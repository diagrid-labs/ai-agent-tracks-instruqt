import asyncio
import itertools
import json
import logging
import random
import re
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass

from dapr.clients import DaprClient
from dapr.clients.grpc._response import BindingResponse
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engineering")


# One warp core reading. The field order is the JSON key order.
@dataclass
class WarpCoreReading:
    readingId: str
    stardate: float
    coreTempK: int
    plasmaFlow: float


# Per-process counter, so the first reading is wc-0001.
_counter = itertools.count(1)


def create_reading() -> WarpCoreReading:
    # Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
    stardate = round(78000.0 + (int(time.time()) - 1767225600) / 3600.0, 1)
    return WarpCoreReading(
        readingId=f"wc-{next(_counter):04d}",
        stardate=stardate,
        coreTempK=random.randint(850, 950),
        plasmaFlow=random.randint(70, 100) / 100,
    )


# The SQL the engineering app runs. Every value goes through $1, $2... placeholders, never
# through string concatenation.
CLEAR_READINGS = "DELETE FROM warp_core_readings"
INSERT_READING = (
    "INSERT INTO warp_core_readings (reading_id, stardate, core_temp_k, plasma_flow) "
    "VALUES ($1, $2, $3, $4)"
)
# The casts and to_char keep the binding's JSON simple: plain numbers and a plain string,
# nothing the app has to decode from a database type.
SELECT_READINGS = (
    "SELECT reading_id, stardate::float8, core_temp_k, plasma_flow::float8, "
    "to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
    "FROM warp_core_readings WHERE core_temp_k >= $1 ORDER BY recorded_at DESC, reading_id DESC LIMIT 20"
)

# The app only knows the output binding's component name, never that PostgreSQL is behind it.
BINDING = "ship-db"
# The state store component name, from resources/statestore.yaml.
STATE_STORE = "statestore"


def state_key(reading_id: str) -> str:
    return f"reading-{reading_id}"


MIN_TEMP_PATTERN = re.compile(r"-?[0-9]{1,6}")

# The one DaprClient of the app. Creating it waits for the sidecar, so it is created in the
# startup thread below; the cron handlers and GET endpoints wait on the gate until it exists.
_client: DaprClient | None = None
_gate = threading.Event()


def _invoke(operation: str, sql: str, args: tuple) -> BindingResponse:
    # The binding name and the operation say where and what; the SQL and its parameters travel
    # as request metadata. "params" is a JSON array in a string, matching $1, $2...
    metadata = {"sql": sql}
    if args:
        metadata["params"] = json.dumps(list(args))
    return _client.invoke_binding(BINDING, operation, binding_metadata=metadata)


def exec_sql(sql: str, *args) -> BindingResponse:
    # "exec" runs a statement that changes data (INSERT, DELETE) and returns no rows.
    return _invoke("exec", sql, args)


def query_sql(sql: str, *args) -> list:
    # "query" runs a SELECT. The binding answers with a JSON array of arrays: one inner list
    # per row, values in the order of the SELECT list, so callers read them by position.
    return json.loads(_invoke("query", sql, args).data)


def _startup_clear() -> None:
    global _client
    try:
        # Creating the client waits for the sidecar, which starts alongside the app.
        _client = DaprClient()
        # Each run starts with an empty table, so readings from an earlier run (or another
        # language) never show up. The app does this itself because Postgres outlives it.
        exec_sql(CLEAR_READINGS)
        logger.info("engineering cleared warp_core_readings for a fresh run")
    except Exception as error:
        logger.warning("engineering could not clear warp_core_readings: %s", error)
    finally:
        # Open the gate even when the clear failed: the app keeps running.
        _gate.set()


# Cron ticks and GET requests wait here, so a reading stored by an early tick is never wiped
# by the clear. The wait runs in a thread so the event loop stays free.
async def _wait_for_gate() -> None:
    await asyncio.to_thread(_gate.wait)


def _binding_failed(error: Exception) -> JSONResponse:
    logger.warning("engineering binding call failed: %s", error)
    return JSONResponse({"error": "BINDING_FAILED"}, status_code=500)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A background thread, so the app starts serving while it waits for the sidecar.
    threading.Thread(target=_startup_clear, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


# An input binding needs no Dapr code at all: the sidecar calls a plain HTTP endpoint whose
# path is the component name (warp-core-scan). No decorator, no Dapr package for the trigger.
@app.post("/warp-core-scan")
async def warp_core_scan() -> Response:
    await _wait_for_gate()
    reading = create_reading()
    logger.info(
        "engineering warp-core scan %s stardate=%.1f coreTempK=%d plasmaFlow=%.2f",
        reading.readingId,
        reading.stardate,
        reading.coreTempK,
        reading.plasmaFlow,
    )
    try:
        # The same reading is written twice, through two different Dapr APIs.
        #
        # 1. State API: Dapr owns the table. We hand over a key and a value, Dapr decides how
        #    to store it (a `state` table with key, JSON value, etag and timestamps). There
        #    is no schema and no SQL in our code, and the call is portable: swap the
        #    statestore component for Redis or Cosmos DB and this line stays the same. The
        #    API also gives us ETags, TTL and transactions for free.
        key = state_key(reading.readingId)
        await asyncio.to_thread(
            _client.save_state,
            STATE_STORE,
            key,
            json.dumps(asdict(reading)),
            # Tell the store the bytes are JSON, so the `state` table holds a real JSON
            # object (readable in psql) instead of an opaque base64 string.
            state_metadata={"contentType": "application/json"},
        )
        logger.info(
            "engineering saved reading %s to statestore (key=%s)", reading.readingId, key
        )

        # 2. Output binding: we own the table. We wrote the schema and we write the SQL, so we
        #    can filter, sort and delete in bulk (see GET /readings). The price is that this
        #    code is tied to Postgres: swapping the ship-db component for another store breaks it.
        await asyncio.to_thread(
            exec_sql,
            INSERT_READING,
            reading.readingId,
            reading.stardate,
            reading.coreTempK,
            reading.plasmaFlow,
        )
    except Exception as error:
        return _binding_failed(error)
    logger.info("engineering stored reading %s in warp_core_readings", reading.readingId)
    # Any 2xx tells Dapr the tick was handled.
    return Response(status_code=200)


# State API read: one reading by key. Get-by-key is all the State API offers for lookups;
# "all readings above 900 K" needs a query, which is what GET /readings does with SQL.
@app.get("/state/{reading_id}")
async def get_state(reading_id: str) -> JSONResponse:
    await _wait_for_gate()
    try:
        state = await asyncio.to_thread(_client.get_state, STATE_STORE, state_key(reading_id))
    except Exception as error:
        return _binding_failed(error)
    # A key that was never saved comes back with empty data, not as an error.
    if not state.data:
        return JSONResponse({"error": "NOT_FOUND"}, status_code=404)
    # The JSONB column does not keep key order, so rebuild the reading to answer in the
    # documented key order.
    return JSONResponse(asdict(WarpCoreReading(**json.loads(state.data))))


# Binding read, with SQL: the filter and the ordering are ours. The State API cannot do this
# against the reading values without a store-specific query.
@app.get("/readings")
async def get_readings(minTemp: str | None = None) -> JSONResponse:
    # Missing minTemp means 0. A present but malformed one (empty, 9.5, abc, too long) is a 400.
    min_temp = 0
    if minTemp is not None:
        if not MIN_TEMP_PATTERN.fullmatch(minTemp):
            return JSONResponse({"error": "INVALID_MIN_TEMP"}, status_code=400)
        min_temp = int(minTemp)

    await _wait_for_gate()
    try:
        # Output binding again, with the "query" operation: it returns rows. Each row is a list
        # whose values follow the SELECT list, so we map them by position.
        rows = await asyncio.to_thread(query_sql, SELECT_READINGS, min_temp)
    except Exception as error:
        return _binding_failed(error)
    return JSONResponse(
        [
            {
                "readingId": row[0],
                "stardate": row[1],
                "coreTempK": row[2],
                "plasmaFlow": row[3],
                "recordedAt": row[4],
            }
            for row in rows
        ]
    )
