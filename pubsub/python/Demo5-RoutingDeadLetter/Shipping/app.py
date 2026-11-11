import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()

# There is no Dapr code here. The routes are wired only by resources/subscription-orders.yaml
# and resources/subscription-dead-letter.yaml: Dapr picks /orders/express or /orders/standard
# from the order's priority, and POSTs dead-lettered messages to /orders/dead.


@app.post("/orders/express")
async def express(request: Request):
    return await handle(request, "express")


@app.post("/orders/standard")
async def standard(request: Request):
    return await handle(request, "standard")


# Dapr forwards the original CloudEvent to orders-dead once the retries are used up,
# so the order is in "data" here too.
@app.post("/orders/dead")
async def dead_letter(request: Request):
    order_id, _ = await read_order(request)
    if order_id is None:
        return dropped()
    logger.info("shipping dead-lettered order %s", order_id)
    return {"status": "SUCCESS"}


async def handle(request: Request, route: str):
    order_id, item = await read_order(request)
    if order_id is None:
        return dropped()
    if item == "poison":
        logger.info("shipping rejected order %s", order_id)
        # A 500 with RETRY makes Dapr redeliver per resources/resiliency.yaml, then dead-letter.
        return JSONResponse(status_code=500, content={"status": "RETRY"})
    logger.info("shipping %s order %s", route, order_id)
    # SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return {"status": "SUCCESS"}


# DROP, not RETRY: an event without an order id will not parse any better on a redelivery.
def dropped():
    logger.info("shipping dropped unreadable event")
    return {"status": "DROP"}


async def read_order(request: Request):
    """Reads data.orderId and data.item from the CloudEvent body; order_id is None if unreadable."""
    try:
        data = (await request.json())["data"]
        order_id = data["orderId"]
        item = data.get("item")
    except (ValueError, KeyError, TypeError, AttributeError):
        return None, None
    return (order_id, item) if isinstance(order_id, str) else (None, None)
