import logging

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()


# There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
# Dapr POSTs each message to this route as a CloudEvent, and the app just reads the JSON.
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
        event = await request.json()
    except ValueError:
        return None
    # The order is in the CloudEvent's "data" field.
    match event:
        case {"data": {"orderId": str(order_id)}}:
            return order_id
    return None
