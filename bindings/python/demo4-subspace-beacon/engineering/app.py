import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import grpc
from dapr.aio.clients import DaprClient
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engineering")


# Fields are snake_case in Python and camelCase in JSON (beacon_id <-> beaconId).
class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True)


# What the beacon answers.
class Ping(CamelModel):
    beacon_id: str
    signal_strength: int
    message: str
    stardate: float


class CommsStatus(CamelModel):
    status: str
    last_signal_strength: int | None


# The SQL the engineering app runs. Every value goes through $1, $2... placeholders, never
# through string concatenation.
CLEAR_COMMS = "DELETE FROM comms_log"
INSERT_PING = (
    "INSERT INTO comms_log (beacon_id, signal_strength, message, stardate) VALUES ($1, $2, $3, $4)"
)
LAST_PINGS = "SELECT signal_strength FROM comms_log ORDER BY id DESC LIMIT 3"


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
            # Each run starts with an empty table, so pings from an earlier run (or another
            # language) never show up. The app does this itself because Postgres outlives it.
            # It happens before the app serves requests, so no cron tick can race the clear.
            await ship_db.exec(CLEAR_COMMS)
            logger.info("engineering cleared comms_log for a fresh run")
        except grpc.RpcError as error:
            logger.warning("engineering could not clear comms_log: %s", error)
        app.state.dapr = client
        app.state.ship_db = ship_db
        yield


app = FastAPI(lifespan=lifespan)


def get_dapr(request: Request) -> DaprClient:
    return request.app.state.dapr


def get_ship_db(request: Request) -> ShipDb:
    return request.app.state.ship_db


DaprDep = Annotated[DaprClient, Depends(get_dapr)]
ShipDbDep = Annotated[ShipDb, Depends(get_ship_db)]


# A failed binding call surfaces as a gRPC error. One handler turns it into the same 500
# for every endpoint, so the endpoints only describe the happy path.
@app.exception_handler(grpc.RpcError)
async def binding_failed(_: Request, error: grpc.RpcError) -> JSONResponse:
    logger.warning("engineering binding call failed: %s", error)
    return JSONResponse({"error": "BINDING_FAILED"}, status_code=500)


# Input binding: the beacon-ping cron component makes the sidecar call this plain HTTP endpoint
# every 5 seconds. The path is the component name. No decorator, no Dapr package for the trigger.
@app.post("/beacon-ping")
async def beacon_ping(dapr: DaprDep, ship_db: ShipDbDep) -> Response:
    try:
        # Service invocation: call the "ping" method of the app with ID subspace-beacon. The
        # sidecar finds the app by its ID, so there is no host or port in this code.
        response = await dapr.invoke_method("subspace-beacon", "ping", http_verb="GET")
        ping = Ping.model_validate_json(response.data)
    except Exception:
        # The beacon may still be starting, so an unreachable beacon is expected: we log it and move on.
        # Answering 200 is deliberate: a 500 would change nothing, because cron ticks are never retried;
        # the next tick simply tries again.
        logger.warning("engineering beacon unreachable")
        return Response(status_code=200)

    try:
        # Output binding: call the component named ship-db with the "exec" operation. The SQL
        # goes in metadata.sql, its values in metadata.params as a JSON array for $1..$4.
        await ship_db.exec(INSERT_PING, ping.beacon_id, ping.signal_strength, ping.message, ping.stardate)
        logger.info(
            'engineering pinged %s signalStrength=%d message="%s"',
            ping.beacon_id,
            ping.signal_strength,
            ping.message,
        )
    except grpc.RpcError as error:
        logger.warning("engineering binding call failed: %s", error)
    return Response(status_code=200)


@app.get("/comms/status", response_model=CommsStatus)
async def comms_status(ship_db: ShipDbDep) -> CommsStatus:
    # Output binding with the "query" operation. Each row is a list whose values follow the
    # SELECT list, so we read the signal by position.
    signals = [row[0] for row in await ship_db.query(LAST_PINGS)]
    established = len(signals) == 3 and all(signal >= 40 for signal in signals)
    # The newest row is first (ORDER BY id DESC). No rows means null.
    return CommsStatus(
        status="ESTABLISHED" if established else "SEARCHING",
        last_signal_strength=signals[0] if signals else None,
    )
