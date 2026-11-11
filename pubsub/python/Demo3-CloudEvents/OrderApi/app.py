import json
import logging
from contextlib import asynccontextmanager

import grpc
from dapr.clients import DaprClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PUBSUB = "pubsub"
FIELDS = ("orderId", "item", "quantity", "priority")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("order-api")

client: DaprClient


@asynccontextmanager
async def lifespan(_: FastAPI):
    # One Dapr client for the app's lifetime, closed on shutdown (the secrets demos open one
    # per request because they make a single call; a publisher reuses its connection).
    global client
    client = DaprClient()
    yield
    client.close()


app = FastAPI(lifespan=lifespan)


@app.post("/orders")
async def publish_order(request: Request):
    # Dapr wraps the order in a CloudEvent: an envelope with id, source, type and the order in "data".
    return await publish(request, "orders", metadata=None)


@app.post("/orders/raw")
async def publish_raw_order(request: Request):
    # The rawPayload publish metadata tells Dapr not to add the envelope: the order itself is
    # the message on the topic. The subscription needs no rawPayload of its own (see subscription-orders-raw.yaml).
    return await publish(request, "orders-raw", metadata={"rawPayload": "true"})


async def publish(request: Request, topic: str, metadata: dict | None):
    order = await read_order(request)
    if order is None:
        return JSONResponse(status_code=400, content={"error": "INVALID_ORDER"})
    try:
        # The app only knows the pub/sub component's name and the topic, never the broker
        # behind them.
        client.publish_event(
            pubsub_name=PUBSUB,
            topic_name=topic,
            data=json.dumps(order, separators=(",", ":")),
            data_content_type="application/json",
            publish_metadata=metadata,
        )
    except grpc.RpcError as e:
        # Show the failure instead of hiding it: the gRPC status name tells the caller why
        # Dapr rejected the publish.
        return JSONResponse(
            status_code=500, content={"orderId": order["orderId"], "error": e.code().name}
        )
    logger.info("order-api published %s to %s", order["orderId"], topic)
    return {"orderId": order["orderId"], "topic": topic}


async def read_order(request: Request):
    """Returns the order with its keys in the contract's order, or None if it is invalid."""
    try:
        body = await request.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or any(field not in body for field in FIELDS):
        return None
    if not all(isinstance(body[f], str) for f in ("orderId", "item", "priority")):
        return None
    if not isinstance(body["quantity"], int) or isinstance(body["quantity"], bool):
        return None
    return {field: body[field] for field in FIELDS}
