import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()


# There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
# Dapr POSTs each message to this route as a CloudEvent, and the app just reads the JSON.
@app.post("/orders")
async def receive_order(request: Request):
    event = await request.json()
    # The order is in the CloudEvent's "data" field.
    data = event.get("data") if isinstance(event, dict) else None
    order_id = data.get("orderId") if isinstance(data, dict) else None
    if not isinstance(order_id, str):
        return JSONResponse(status_code=400, content={"error": "INVALID_EVENT"})
    logger.info("shipping received order %s", order_id)
    # SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return {"status": "SUCCESS"}
