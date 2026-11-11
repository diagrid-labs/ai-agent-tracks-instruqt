import logging

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()


# There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
# Dapr POSTs each message to this route as a CloudEvent, and the app just reads the JSON.
@app.post("/orders")
async def receive_order(request: Request):
    event = await request.json()
    # The order is in the CloudEvent's "data" field.
    logger.info("shipping received order %s", event["data"]["orderId"])
    # SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return {"status": "SUCCESS"}
