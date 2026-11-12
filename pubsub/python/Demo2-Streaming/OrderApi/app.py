import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict

import grpc
from dapr.aio.clients import DaprClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PUBSUB = "pubsub"
TOPIC = "orders"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("order-api")


class Order(TypedDict):
    orderId: str
    item: str
    quantity: int
    priority: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One Dapr client for the app's lifetime (the secrets demos open one per request because
    # they make a single call; a publisher reuses its connection). It is the async client, so
    # publishing doesn't block the server, and `async with` closes it on shutdown.
    async with DaprClient() as client:
        app.state.dapr = client
        yield


app = FastAPI(lifespan=lifespan)


@app.post("/orders")
async def publish_order(request: Request) -> JSONResponse:
    order = await read_order(request)
    if order is None:
        return JSONResponse(status_code=400, content={"error": "INVALID_ORDER"})
    client: DaprClient = request.app.state.dapr
    try:
        # The app only knows the pub/sub component's name and the topic, never the broker
        # behind them. Dapr wraps the order in a CloudEvent and sends it to every subscriber.
        await client.publish_event(
            pubsub_name=PUBSUB,
            topic_name=TOPIC,
            data=json.dumps(order, separators=(",", ":")),
            data_content_type="application/json",
        )
    except grpc.RpcError as e:
        # Show the failure instead of hiding it: the gRPC status name tells the caller why
        # Dapr rejected the publish.
        return JSONResponse(
            status_code=500, content={"orderId": order["orderId"], "error": e.code().name}
        )
    logger.info("order-api published %s to %s", order["orderId"], TOPIC)
    return JSONResponse({"orderId": order["orderId"], "topic": TOPIC})


async def read_order(request: Request) -> Order | None:
    """Returns the order with its keys in the contract's order, or None if it is invalid."""
    try:
        body = await request.json()
    except ValueError:
        return None
    # All four fields, with the right JSON types (a bool is not a quantity); extra fields are ignored.
    match body:
        case {
            "orderId": str(order_id),
            "item": str(item),
            "quantity": int(quantity),
            "priority": str(priority),
        } if not isinstance(quantity, bool):
            return Order(orderId=order_id, item=item, quantity=quantity, priority=priority)
    return None
