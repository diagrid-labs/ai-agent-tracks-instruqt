import logging
import signal
import threading

from dapr.clients import DaprClient

# The SDK's own streaming examples import these from the private _response module: dapr 1.19
# has no public re-export of them.
from dapr.clients.grpc._response import TopicEventResponse, TopicEventResponseStatus
from dapr.common.pubsub.subscription import SubscriptionMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("warehouse")


def receive_order(message: SubscriptionMessage) -> TopicEventResponse:
    # The handler gets the CloudEvent from the stream. For JSON data the SDK has already parsed
    # the order into a dict; anything it could not parse is not a dict here.
    match message.data():
        case {"orderId": str(order_id)}:
            logger.info("warehouse received order %s", order_id)
        case _:
            logger.warning("warehouse dropped unreadable event")
    # This demo always acknowledges: success tells Dapr the message is done. The handler never
    # raises either: the SDK would send no answer for that message, and would close the stream
    # and open a new one.
    return TopicEventResponse(TopicEventResponseStatus.success)


def main() -> None:
    stop = threading.Event()
    # warehouse has no HTTP server, so the main thread waits here until SIGTERM or Ctrl+C.
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    with DaprClient() as client:
        # The app opens the stream itself: pub/sub component `pubsub`, topic `orders`.
        # No Subscription file and no /dapr/subscribe endpoint are involved. The SDK reads the
        # stream on its own thread and calls receive_order for one message at a time.
        close_subscription = client.subscribe_with_handler(
            pubsub_name="pubsub", topic="orders", handler_fn=receive_order
        )
        try:
            stop.wait()
        finally:
            # Closes the stream and waits up to 5 seconds for the SDK's thread to finish.
            close_subscription()


if __name__ == "__main__":
    main()
