import logging

from dapr.ext.fastapi import DaprApp
from fastapi import Body, FastAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("invoicing")

app = FastAPI()
# DaprApp serves /dapr/subscribe, the endpoint Dapr calls at startup to learn this app's
# subscriptions. That is what makes the subscription programmatic.
dapr_app = DaprApp(app)


# The subscription lives in code: pub/sub component `pubsub`, topic `orders`. The handler
# receives the CloudEvent as a dict; the order is in its "data" field.
@dapr_app.subscribe(pubsub="pubsub", topic="orders", route="/orders")
def receive_order(event_data=Body()):
    logger.info("invoicing received order %s", event_data["data"]["orderId"])
