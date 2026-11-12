import logging

from cloudevents.core.bindings import http
from cloudevents.core.exceptions import BaseCloudEventException
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shipping")

app = FastAPI()

# There is no Dapr code here: both routes log exactly the bytes Dapr sends. The subscriptions
# live in resources/*.yaml.


# /orders is a normal subscription: the body is a CloudEvent envelope with the order in "data".
@app.post("/orders")
async def receive_order(request: Request) -> dict[str, str]:
    body = await request.body()
    logger.info("shipping received with envelope: %s", body.decode("utf-8"))
    try:
        # Dapr delivers a standard CloudEvent, so the open CloudEvents SDK can read it with no
        # Dapr dependency. Dapr uses structured mode: the whole event, attributes included, is
        # the JSON body, so the parser reads only the body and no headers are passed.
        event = http.from_structured_event(http.HTTPMessage({}, body))
    except (BaseCloudEventException, ValueError, TypeError, AttributeError):
        # Not a CloudEvent: the raw line above already shows what arrived.
        pass
    else:
        logger.info(
            "shipping parsed CloudEvent id=%s type=%s source=%s",
            event.get_id(), event.get_type(), event.get_source(),
        )
    # SUCCESS tells Dapr the message is handled, so it is not redelivered.
    return {"status": "SUCCESS"}


# /orders-raw receives what the publisher put on the topic: the order itself, no envelope.
# It is not a CloudEvent, so there is nothing for the CloudEvents SDK to read.
@app.post("/orders-raw")
async def receive_raw_order(request: Request) -> dict[str, str]:
    logger.info("shipping received raw: %s", (await request.body()).decode("utf-8"))
    return {"status": "SUCCESS"}
