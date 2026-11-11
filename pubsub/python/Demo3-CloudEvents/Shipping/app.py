import logging

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()

# There is no Dapr code here: both routes log exactly the bytes Dapr sends. The subscriptions
# live in resources/*.yaml.


# /orders is a normal subscription: the body is a CloudEvent envelope with the order in "data".
@app.post("/orders")
async def receive_order(request: Request):
    logger.info("shipping received with envelope: %s", (await request.body()).decode("utf-8"))
    # SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return {"status": "SUCCESS"}


# /orders-raw receives what the publisher put on the topic: the order itself, no envelope.
@app.post("/orders-raw")
async def receive_raw_order(request: Request):
    logger.info("shipping received raw: %s", (await request.body()).decode("utf-8"))
    return {"status": "SUCCESS"}
