import logging

from cloudevents.core.bindings import http
from cloudevents.core.exceptions import BaseCloudEventException
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()


# There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
# Dapr POSTs each message to this route as a CloudEvent, and the app reads it with the
# CloudEvents SDK.
@app.post("/orders")
async def receive_order(request: Request) -> dict[str, str]:
    order_id = await read_order_id(request)
    if order_id is None:
        # DROP, not an error status: Dapr redelivers on any non-2xx answer (except 404), and an
        # unreadable event will not parse any better on a redelivery.
        logger.warning("shipping dropped unreadable event")
        return {"status": "DROP"}
    logger.info("shipping received order %s", order_id)
    # SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return {"status": "SUCCESS"}


async def read_order_id(request: Request) -> str | None:
    """Returns data.orderId from the CloudEvent body, or None if the event is unreadable."""
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
        case {"orderId": str(order_id)}:
            return order_id
    return None
