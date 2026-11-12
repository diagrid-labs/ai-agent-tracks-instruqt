import logging
from typing import NamedTuple

from cloudevents.core.bindings import http
from cloudevents.core.exceptions import BaseCloudEventException
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()

# There is no Dapr code here. The routes are wired only by resources/subscription-orders.yaml
# and resources/subscription-dead-letter.yaml: Dapr picks /orders/express or /orders/standard
# from the order's priority, and POSTs dead-lettered messages to /orders/dead.


class Order(NamedTuple):
    order_id: str
    item: str | None  # None when the event has no string item


@app.post("/orders/express")
async def express(request: Request) -> JSONResponse:
    return await handle(request, "express")


@app.post("/orders/standard")
async def standard(request: Request) -> JSONResponse:
    return await handle(request, "standard")


# Dapr forwards the original CloudEvent to orders-dead once the retries are used up,
# so the order is in "data" here too.
@app.post("/orders/dead")
async def dead_letter(request: Request) -> JSONResponse:
    order = await read_order(request)
    if order is None:
        return dropped()
    logger.info("shipping dead-lettered order %s", order.order_id)
    return JSONResponse({"status": "SUCCESS"})


async def handle(request: Request, priority: str) -> JSONResponse:
    order = await read_order(request)
    if order is None:
        return dropped()
    if order.item == "poison":
        logger.warning("shipping rejected order %s", order.order_id)
        # A 500 with RETRY makes Dapr redeliver per resources/resiliency.yaml, then dead-letter.
        return JSONResponse(status_code=500, content={"status": "RETRY"})
    logger.info("shipping %s order %s", priority, order.order_id)
    # SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return JSONResponse({"status": "SUCCESS"})


# DROP, not RETRY: an event without an order id will not parse any better on a redelivery.
def dropped() -> JSONResponse:
    logger.warning("shipping dropped unreadable event")
    return JSONResponse({"status": "DROP"})


async def read_order(request: Request) -> Order | None:
    """Reads data.orderId and data.item from the CloudEvent body; None if the event is unreadable."""
    try:
        # Dapr delivers a standard CloudEvent, so the open CloudEvents SDK can read it with no
        # Dapr dependency. Dapr uses structured mode: the whole event, attributes included, is
        # the JSON body, so the parser reads only the body and no headers are passed.
        message = http.HTTPMessage({}, await request.body())
        event = http.from_structured_event(message)
    except (BaseCloudEventException, ValueError, TypeError, AttributeError):
        # Bad JSON, a body that is not an object, and a missing or invalid attribute each raise
        # a different error.
        return None
    # The order is in the event's data, which the JSON format hands over as a dict.
    match event.get_data():
        case {"orderId": str(order_id)} as data:
            item = data.get("item")
            return Order(order_id, item if isinstance(item, str) else None)
    return None
