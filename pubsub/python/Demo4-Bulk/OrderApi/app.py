import json
import logging
from contextlib import asynccontextmanager

import grpc
from dapr.clients import DaprClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PUBSUB = "pubsub"
TOPIC = "orders"
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
    order = await read_order(request)
    if order is None:
        return JSONResponse(status_code=400, content={"error": "INVALID_ORDER"})
    try:
        # The app only knows the pub/sub component's name and the topic, never the broker
        # behind them. Dapr wraps the order in a CloudEvent and sends it to every subscriber.
        client.publish_event(
            pubsub_name=PUBSUB,
            topic_name=TOPIC,
            data=json.dumps(order),
            data_content_type="application/json",
        )
    except grpc.RpcError as e:
        return JSONResponse(
            status_code=500, content={"orderId": order["orderId"], "error": e.code().name}
        )
    logger.info("order-api published %s to %s", order["orderId"], TOPIC)
    return {"orderId": order["orderId"], "topic": TOPIC}


@app.post("/orders/bulk")
async def publish_bulk(count: str | None = None, prefix: str = "o"):
    # count must be a whole number from 1 to 100.
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= 100:
        return JSONResponse(status_code=400, content={"error": "INVALID_COUNT"})
    orders = [
        {"orderId": f"{prefix}-{i}", "item": "coffee-beans", "quantity": 1, "priority": "standard"}
        for i in range(1, n + 1)
    ]
    try:
        # One call publishes all orders. Dapr still wraps each one in its own CloudEvent.
        # A bulk publish can succeed for some entries and fail for others, so the response
        # lists the entries that failed instead of raising for them.
        response = client.publish_events(
            pubsub_name=PUBSUB,
            topic_name=TOPIC,
            data=[json.dumps(o) for o in orders],
            data_content_type="application/json",
        )
    except grpc.RpcError as e:
        # Show the failure instead of hiding it: the gRPC status name tells the caller why
        # Dapr rejected the publish. There is no single order to name, so no orderId.
        return JSONResponse(status_code=500, content={"error": e.code().name})
    failed = len(response.failed_entries)
    logger.info("order-api bulk published %d orders to %s, %d failed", n, TOPIC, failed)
    return {"sent": n, "failed": failed}


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
