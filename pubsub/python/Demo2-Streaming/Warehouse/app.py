import json
import logging
import signal
import threading

from dapr.clients import DaprClient
from dapr.clients.grpc._response import TopicEventResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("warehouse")


def receive_order(message):
    # The handler gets the CloudEvent from the stream; the order is in its data field,
    # as a dict or as raw JSON depending on the content type.
    data = message.data()
    if isinstance(data, (bytes, str)):
        data = json.loads(data)
    logger.info("warehouse received order %s", data["orderId"])
    # This demo always acknowledges: "success" tells Dapr the message is done.
    return TopicEventResponse("success")


stop = threading.Event()
# warehouse has no HTTP server, so the main thread waits here until SIGTERM or Ctrl+C.
signal.signal(signal.SIGTERM, lambda *_: stop.set())
signal.signal(signal.SIGINT, lambda *_: stop.set())

with DaprClient() as client:
    # The app opens the stream itself: pub/sub component `pubsub`, topic `orders`.
    # No Subscription file and no /dapr/subscribe endpoint are involved.
    close_subscription = client.subscribe_with_handler(
        pubsub_name="pubsub", topic="orders", handler_fn=receive_order
    )
    stop.wait()
    close_subscription()
