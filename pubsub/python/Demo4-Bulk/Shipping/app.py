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
async def receive_batch(request: Request):
    # The body is {"entries": [{"entryId", "event", ...}, ...], ...}: one entry per message.
    try:
        entries = (await request.json())["entries"]
        if not isinstance(entries, list):
            raise TypeError("entries is not a list")
    except (ValueError, KeyError, TypeError):
        # Not a bulk envelope at all: a non-2xx answer makes Dapr treat the delivery as failed.
        return JSONResponse(status_code=400, content={"error": "INVALID_BULK_REQUEST"})
    ids = []
    statuses = []
    for entry in entries:
        entry_id = entry.get("entryId", "") if isinstance(entry, dict) else ""
        order_id = read_order_id(entry)
        if order_id is None:
            # DROP, not RETRY: a malformed entry will not parse any better on a redelivery.
            logger.info("shipping dropped unreadable entry %s", entry_id)
            statuses.append({"entryId": entry_id, "status": "DROP"})
            continue
        ids.append(order_id)
        statuses.append({"entryId": entry_id, "status": "SUCCESS"})
    logger.info("shipping received batch of %d orders: %s", len(ids), ",".join(ids))
    # Bulk subscriptions are acknowledged per entry: Dapr redelivers only the entries that
    # are not SUCCESS.
    return {"statuses": statuses}


def read_order_id(entry):
    """Returns entry.event.data.orderId, or None if the entry is unreadable."""
    try:
        event = entry["event"]
        # "event" is the CloudEvent; depending on the content type it is an object or a JSON string.
        if isinstance(event, str):
            event = json.loads(event)
        order_id = event["data"]["orderId"]
    except (ValueError, KeyError, TypeError):
        return None
    return order_id if isinstance(order_id, str) else None
