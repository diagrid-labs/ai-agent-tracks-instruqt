import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager

from dapr.clients import DaprClient
from dapr.clients.grpc._response import BindingResponse
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engineering")


# The SQL the engineering app runs. Every value goes through $1, $2... placeholders, never
# through string concatenation.
CLEAR_COMMS = "DELETE FROM comms_log"
INSERT_PING = (
    "INSERT INTO comms_log (beacon_id, signal_strength, message, stardate) VALUES ($1, $2, $3, $4)"
)
LAST_PINGS = "SELECT signal_strength FROM comms_log ORDER BY id DESC LIMIT 3"

# The app only knows the output binding's component name, never that PostgreSQL is behind it.
BINDING = "ship-db"

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
        # Each run starts with an empty table, so pings from an earlier run (or another
        # language) never show up. The app does this itself because Postgres outlives it.
        exec_sql(CLEAR_COMMS)
        logger.info("engineering cleared comms_log for a fresh run")
    except Exception as error:
        logger.warning("engineering could not clear comms_log: %s", error)
    finally:
        # Open the gate even when the clear failed: the app keeps running.
        _gate.set()


# Cron ticks and GET requests wait here, so a ping stored by an early tick is never wiped
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


# Input binding: the beacon-ping cron component makes the sidecar call this plain HTTP endpoint
# every 5 seconds. The path is the component name. No decorator, no Dapr package for the trigger.
@app.post("/beacon-ping")
async def beacon_ping() -> Response:
    await _wait_for_gate()
    try:
        # Service invocation: call the "ping" method of the app with ID subspace-beacon. The
        # sidecar finds the app by its ID, so there is no host or port in this code.
        response = await asyncio.to_thread(_client.invoke_method, "subspace-beacon", "ping", http_verb="GET")
        ping = json.loads(response.data)
        beacon_id = ping["beaconId"]
        signal_strength = ping["signalStrength"]
        message = ping["message"]
        stardate = ping["stardate"]
    except Exception:
        # The beacon may still be starting. Answer 200 anyway, so the sidecar does not log a
        # binding error on every tick; the next tick tries again.
        logger.warning("engineering beacon unreachable")
        return Response(status_code=200)

    try:
        # Output binding: call the component named ship-db with the "exec" operation. The SQL
        # goes in metadata.sql, its values in metadata.params as a JSON array for $1..$4.
        await asyncio.to_thread(exec_sql, INSERT_PING, beacon_id, signal_strength, message, stardate)
        logger.info(
            'engineering pinged %s signalStrength=%d message="%s"', beacon_id, signal_strength, message
        )
    except Exception as error:
        logger.warning("engineering binding call failed: %s", error)
    return Response(status_code=200)


@app.get("/comms/status")
async def comms_status() -> JSONResponse:
    await _wait_for_gate()
    try:
        # Output binding with the "query" operation. Each row is a list whose values follow the
        # SELECT list, so we read the signal by position.
        rows = await asyncio.to_thread(query_sql, LAST_PINGS)
        signals = [row[0] for row in rows]
    except Exception as error:
        return _binding_failed(error)
    established = len(signals) == 3 and all(signal >= 40 for signal in signals)
    # The newest row is first (ORDER BY id DESC). No rows means null.
    return JSONResponse(
        {
            "status": "ESTABLISHED" if established else "SEARCHING",
            "lastSignalStrength": signals[0] if signals else None,
        }
    )
