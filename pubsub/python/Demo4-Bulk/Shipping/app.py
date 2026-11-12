import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()

# There is no Dapr code here: the route is wired only by resources/subscription-bulk.yaml,
# and Dapr POSTs a batch of messages as one request.


@app.post("/orders/bulk")
async def receive_batch(request: Request) -> JSONResponse:
    # The body is {"entries": [{"entryId", "event", ...}, ...], ...}: one entry per message.
    try:
        body = await request.json()
    except ValueError:
        body = None
    entries = body.get("entries") if isinstance(body, dict) else None
    if not isinstance(entries, list):
        # Not a bulk envelope at all: a non-2xx answer makes Dapr treat the delivery as failed.
        return JSONResponse(status_code=400, content={"error": "INVALID_BULK_REQUEST"})
    ids: list[str] = []
    statuses: list[dict[str, object]] = []
    for entry in entries:
        entry_id = entry.get("entryId", "") if isinstance(entry, dict) else ""
        order_id = read_order_id(entry)
        if order_id is None:
            # DROP, not RETRY: a malformed entry will not parse any better on a redelivery.
            logger.warning("shipping dropped unreadable entry %s", entry_id)
            statuses.append({"entryId": entry_id, "status": "DROP"})
            continue
        ids.append(order_id)
        statuses.append({"entryId": entry_id, "status": "SUCCESS"})
    logger.info("shipping received batch of %d orders: %s", len(ids), ",".join(ids))
    # Bulk subscriptions are acknowledged per entry: Dapr redelivers only the entries that
    # are not SUCCESS.
    return JSONResponse({"statuses": statuses})


def read_order_id(entry: object) -> str | None:
    """Returns entry.event.data.orderId, or None if the entry is unreadable."""
    event = entry.get("event") if isinstance(entry, dict) else None
    # "event" is the CloudEvent; depending on the content type it is an object or a JSON string.
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except ValueError:
            return None
    match event:
        case {"data": {"orderId": str(order_id)}}:
            return order_id
    return None
