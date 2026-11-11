import json
import logging

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()

# There is no Dapr code here: the route is wired only by resources/subscription-bulk.yaml,
# and Dapr POSTs a batch of messages as one request.


@app.post("/orders/bulk")
async def receive_batch(request: Request):
    # The body is {"entries": [{"entryId", "event", ...}, ...], ...}: one entry per message.
    entries = (await request.json())["entries"]
    ids = []
    for entry in entries:
        event = entry["event"]
        # "event" is the CloudEvent; depending on the content type it is an object or a JSON string.
        if isinstance(event, str):
            event = json.loads(event)
        ids.append(event["data"]["orderId"])
    logger.info("shipping received batch of %d orders: %s", len(ids), ",".join(ids))
    # Bulk subscriptions are acknowledged per entry: Dapr redelivers only the entries that
    # are not SUCCESS.
    return {"statuses": [{"entryId": e["entryId"], "status": "SUCCESS"} for e in entries]}
