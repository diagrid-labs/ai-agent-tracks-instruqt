import itertools
import json
import logging
import random
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import grpc
from dapr.aio.clients import DaprClient
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engineering")


# Fields are snake_case in Python and camelCase in JSON (reading_id <-> readingId).
class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True)


# One warp core reading. The field order is the JSON key order.
class WarpCoreReading(CamelModel):
    reading_id: str
    stardate: float
    core_temp_k: int
    plasma_flow: float


# A stored reading, as GET /readings returns it.
class ReadingRow(WarpCoreReading):
    recorded_at: str


# Per-process counter, so the first reading is wc-0001.
_counter = itertools.count(1)


def create_reading() -> WarpCoreReading:
    # Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
    stardate = round(78000.0 + (int(time.time()) - 1767225600) / 3600.0, 1)
    return WarpCoreReading(
        reading_id=f"wc-{next(_counter):04d}",
        stardate=stardate,
        core_temp_k=random.randint(850, 950),
        plasma_flow=random.randint(70, 100) / 100,
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
PURGE_READINGS = "DELETE FROM warp_core_readings WHERE recorded_at < now() - interval '1 minute'"

MIN_TEMP_PATTERN = re.compile(r"-?[0-9]{1,6}")


# Thin wrapper around the ship-db output binding. The app only knows the component name
# "ship-db", never that PostgreSQL is behind it.
class ShipDb:
    BINDING = "ship-db"

    def __init__(self, client: DaprClient) -> None:
        self._client = client

    async def exec(self, sql: str, *args: object) -> None:
        # "exec" runs a statement that changes data (INSERT, DELETE) and returns no rows.
        await self._invoke("exec", sql, args)

    async def query(self, sql: str, *args: object) -> list[list]:
        # "query" runs a SELECT. The binding answers with a JSON array of arrays: one inner
        # list per row, values in the order of the SELECT list, so callers read them by position.
        response = await self._invoke("query", sql, args)
        return json.loads(response.data)

    async def _invoke(self, operation: str, sql: str, args: tuple):
        # The binding name and the operation say where and what; the SQL and its parameters
        # travel as request metadata. "params" is a JSON array in a string, matching $1, $2...
        metadata = {"sql": sql}
        if args:
            metadata["params"] = json.dumps(args)
        return await self._client.invoke_binding(self.BINDING, operation, binding_metadata=metadata)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One async Dapr client for the app's lifetime. Creating it waits for the sidecar, and
    # `async with` closes it on shutdown.
    async with DaprClient() as client:
        ship_db = ShipDb(client)
        try:
            # Each run starts with an empty table, so readings from an earlier run (or another
            # language) never show up. The app does this itself because Postgres outlives it.
            # It happens before the app serves requests, so no cron tick can race the clear.
            await ship_db.exec(CLEAR_READINGS)
            logger.info("engineering cleared warp_core_readings for a fresh run")
        except grpc.RpcError as error:
            logger.warning("engineering could not clear warp_core_readings: %s", error)
        app.state.ship_db = ship_db
        yield


app = FastAPI(lifespan=lifespan)


def get_ship_db(request: Request) -> ShipDb:
    return request.app.state.ship_db


ShipDbDep = Annotated[ShipDb, Depends(get_ship_db)]


# A failed binding call surfaces as a gRPC error. One handler turns it into the same 500
# for every endpoint, so the endpoints only describe the happy path.
@app.exception_handler(grpc.RpcError)
async def binding_failed(_: Request, error: grpc.RpcError) -> JSONResponse:
    logger.warning("engineering binding call failed: %s", error)
    return JSONResponse({"error": "BINDING_FAILED"}, status_code=500)


# An input binding needs no Dapr code at all: the sidecar calls a plain HTTP endpoint whose
# path is the component name (warp-core-scan). No decorator, no Dapr package for the trigger.
@app.post("/warp-core-scan")
async def warp_core_scan(ship_db: ShipDbDep) -> Response:
    reading = create_reading()
    logger.info(
        "engineering warp-core scan %s stardate=%.1f coreTempK=%d plasmaFlow=%.2f",
        reading.reading_id,
        reading.stardate,
        reading.core_temp_k,
        reading.plasma_flow,
    )
    # Output binding: call the component named ship-db with the "exec" operation. The SQL
    # goes in metadata.sql, its values in metadata.params as a JSON array for $1..$4.
    await ship_db.exec(
        INSERT_READING,
        reading.reading_id,
        reading.stardate,
        reading.core_temp_k,
        reading.plasma_flow,
    )
    logger.info("engineering stored reading %s in warp_core_readings", reading.reading_id)
    # Any 2xx tells Dapr the tick was handled.
    return Response(status_code=200)


# A second cron binding drives the clean-up. It is an "exec" again: the delete changes data
# and returns no rows.
@app.post("/purge-old-readings")
async def purge_old_readings(ship_db: ShipDbDep) -> Response:
    await ship_db.exec(PURGE_READINGS)
    logger.info("engineering purged old readings")
    return Response(status_code=200)


@app.get("/readings", response_model=list[ReadingRow])
async def get_readings(
    ship_db: ShipDbDep,
    min_temp: Annotated[str | None, Query(alias="minTemp")] = None,
):
    # Missing minTemp means 0. A present but malformed one (empty, 9.5, abc, too long) is a 400.
    if min_temp is not None and not MIN_TEMP_PATTERN.fullmatch(min_temp):
        return JSONResponse({"error": "INVALID_MIN_TEMP"}, status_code=400)

    # Output binding again, with the "query" operation: it returns rows. Each row is a list
    # whose values follow the SELECT list, so we map them by position.
    rows = await ship_db.query(SELECT_READINGS, int(min_temp or 0))
    return [
        ReadingRow(
            reading_id=row[0],
            stardate=row[1],
            core_temp_k=row[2],
            plasma_flow=row[3],
            recorded_at=row[4],
        )
        for row in rows
    ]
