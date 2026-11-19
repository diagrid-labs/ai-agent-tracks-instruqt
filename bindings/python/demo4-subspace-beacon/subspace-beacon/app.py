import itertools
import logging
import time

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subspace-beacon")

# The beacon is a plain HTTP app: no Dapr SDK, no Dapr code. Engineering calls it through
# service invocation, and the Dapr sidecar next to this app delivers the request here.
app = FastAPI()

# Signal strength walks through a fixed sequence, then stays at the last value. The counter
# is per process, so restarting the beacon restarts the sequence.
SEQUENCE = [12, 27, 45, 63, 81, 94]
_calls = itertools.count()


# Fields are snake_case in Python and camelCase in JSON (beacon_id <-> beaconId).
# The field order is the JSON key order.
class Ping(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True)

    beacon_id: str
    signal_strength: int
    message: str
    stardate: float


# An async endpoint runs on the event loop, one request at a time between awaits, so the
# counter needs no lock.
@app.get("/ping")
async def ping() -> Ping:
    signal_strength = SEQUENCE[min(next(_calls), len(SEQUENCE) - 1)]
    if signal_strength < 40:
        message = "static"
    elif signal_strength < 80:
        message = "signal acquired"
    else:
        message = "channel open"
    # Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
    stardate = round(78000.0 + (int(time.time()) - 1767225600) / 3600.0, 1)
    logger.info("subspace-beacon answered ping signalStrength=%d", signal_strength)
    return Ping(beacon_id="relay-theta-9", signal_strength=signal_strength, message=message, stardate=stardate)
