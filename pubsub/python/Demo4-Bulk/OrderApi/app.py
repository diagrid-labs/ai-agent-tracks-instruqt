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

INT32_MIN, INT32_MAX = -(2**31), 2**31 - 1


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


@app.post("/orders/bulk")
async def publish_bulk(request: Request, count: str | None = None, prefix: str = "o") -> JSONResponse:
    # count is a str, not an int: with int, FastAPI would answer "abc" with its own 422 before
    # this code runs. count must be a whole number from 1 to 100 in plain ASCII digits (int()
    # alone would also take "+5" and "1_0"); surrounding whitespace is ignored.
    digits = (count or "").strip()
    try:
        n = int(digits) if digits.isascii() and digits.isdigit() else 0
    except ValueError:  # thousands of digits: more than int() will read from a string
        n = 0
    if not 1 <= n <= 100:
        return JSONResponse(status_code=400, content={"error": "INVALID_COUNT"})
    prefix = prefix or "o"
    orders = [
        Order(orderId=f"{prefix}-{i}", item="coffee-beans", quantity=1, priority="standard")
        for i in range(1, n + 1)
    ]
    client: DaprClient = request.app.state.dapr
    try:
        # One call publishes all orders. Dapr still wraps each one in its own CloudEvent.
        # A bulk publish can succeed for some entries and fail for others, so the response
        # lists the entries that failed instead of raising for them.
        response = await client.publish_events(
            pubsub_name=PUBSUB,
            topic_name=TOPIC,
            data=[json.dumps(o, separators=(",", ":")) for o in orders],
            data_content_type="application/json",
        )
    except grpc.RpcError as e:
        # Show the failure instead of hiding it: the gRPC status name tells the caller why
        # Dapr rejected the publish. There is no single order to name, so no orderId.
        return JSONResponse(status_code=500, content={"error": e.code().name})
    failed = len(response.failed_entries)
    logger.info("order-api bulk published %d orders to %s, %d failed", n, TOPIC, failed)
    return JSONResponse({"sent": n, "failed": failed})


async def read_order(request: Request) -> Order | None:
    """Returns the order with its keys in the contract's order, or None if it is invalid."""
    try:
        body = await request.json()
    except ValueError:
        return None
    # All four fields, with the right JSON types (a bool is not a quantity); extra fields are ignored.
    # The quantity must fit a 32-bit int, the same limit as the .NET and Java versions.
    match body:
        case {
            "orderId": str(order_id),
            "item": str(item),
            "quantity": int(quantity),
            "priority": str(priority),
        } if not isinstance(quantity, bool) and INT32_MIN <= quantity <= INT32_MAX:
            return Order(orderId=order_id, item=item, quantity=quantity, priority=priority)
    return None
