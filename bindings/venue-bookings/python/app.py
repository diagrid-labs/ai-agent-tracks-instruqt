"""Save and query venue bookings through a PostgreSQL output binding."""

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated

from dapr.clients import DaprClient
from dapr.clients.exceptions import DaprInternalError
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from grpc import RpcError
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BINDING_NAME = "postgres-binding"


@asynccontextmanager
async def lifespan(app: FastAPI):
    with DaprClient() as client:
        app.state.dapr_client = client
        yield


app = FastAPI(lifespan=lifespan)


def get_dapr_client(request: Request) -> DaprClient:
    return request.app.state.dapr_client


DaprDependency = Annotated[DaprClient, Depends(get_dapr_client)]


class BookingRequest(BaseModel):
    venue: str
    event_date: str


class Booking(BookingRequest):
    id: int


class SaveBookingResponse(BaseModel):
    status: str
    rows_affected: str | None


class BookingsResponse(BaseModel):
    bookings: list[Booking]


@app.exception_handler(RpcError)
@app.exception_handler(DaprInternalError)
async def binding_error(request: Request, exc: Exception):
    logger.error("Postgres binding request failed", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Postgres binding request failed. Check the Dapr sidecar and database."},
    )


@app.post("/bookings", response_model=SaveBookingResponse)
def create_booking(booking: BookingRequest, client: DaprDependency):
    response = client.invoke_binding(
        binding_name=BINDING_NAME,
        operation="exec",
        data=b"",
        binding_metadata={
            "sql": "INSERT INTO bookings (venue, event_date) VALUES ($1, $2)",
            "params": json.dumps([booking.venue, booking.event_date]),
        },
    )
    rows_affected = response.binding_metadata.get("rows-affected")
    logger.info(
        "Inserted booking for %s on %s (rows-affected=%s)",
        booking.venue,
        booking.event_date,
        rows_affected,
    )
    return SaveBookingResponse(status="saved", rows_affected=rows_affected)


@app.get("/bookings", response_model=BookingsResponse)
def list_bookings(client: DaprDependency):
    response = client.invoke_binding(
        binding_name=BINDING_NAME,
        operation="query",
        data=b"",
        binding_metadata={
            "sql": "SELECT id, venue, event_date::text FROM bookings ORDER BY id",
            "params": "[]",
        },
    )
    rows = json.loads(response.data) if response.data else []
    bookings = [Booking(id=row[0], venue=row[1], event_date=row[2]) for row in rows]
    logger.info("Queried %d booking(s)", len(bookings))
    return BookingsResponse(bookings=bookings)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("APP_PORT", "8006")))
