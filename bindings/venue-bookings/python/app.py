"""Venue Bookings — Dapr Bindings API demo (PostgreSQL output binding).

Two endpoints, one Dapr binding component:
- POST /bookings  calls the binding with operation "exec"  (INSERT a row)
- GET  /bookings  calls the binding with operation "query" (SELECT the rows)

There is only one binding here, bindings.postgresql, which is output-only. Dapr has no
"input binding" for Postgres: an input binding is something that triggers your app (like
a Cron schedule), and Postgres has no mechanism for that. Both endpoints below call the
same binding, just with a different "operation".
"""

import json
import logging
import os

from dapr.clients import DaprClient
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)

BINDING_NAME = "postgres-binding"

app = FastAPI()


class Booking(BaseModel):
    venue: str
    event_date: str


@app.post("/bookings")
def create_booking(booking: Booking):
    """Save a booking with the binding's "exec" operation (an INSERT)."""
    with DaprClient() as client:
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
    logging.info("Inserted booking for %s on %s (rows-affected=%s)", booking.venue, booking.event_date, rows_affected)
    return {"status": "saved", "rows_affected": rows_affected}


@app.get("/bookings")
def list_bookings():
    """Read every booking back with the same binding's "query" operation (a SELECT)."""
    with DaprClient() as client:
        response = client.invoke_binding(
            binding_name=BINDING_NAME,
            operation="query",
            data=b"",
            binding_metadata={
                "sql": "SELECT id, venue, event_date FROM bookings ORDER BY id",
                "params": "[]",
            },
        )
    rows = json.loads(response.data) if response.data else []
    bookings = [{"id": row[0], "venue": row[1], "event_date": row[2]} for row in rows]
    logging.info("Queried %d booking(s)", len(bookings))
    return {"bookings": bookings}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("APP_PORT", "8006")))
