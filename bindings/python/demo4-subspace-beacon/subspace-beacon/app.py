import itertools
import logging
import threading
import time

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subspace-beacon")

# The beacon is a plain HTTP app: no Dapr SDK, no Dapr code. Engineering calls it through
# service invocation, and the Dapr sidecar next to this app delivers the request here.
app = FastAPI()

# Signal strength walks through a fixed sequence, then stays at the last value. The counter
# is per process, so restarting the beacon restarts the sequence.
SEQUENCE = [12, 27, 45, 63, 81, 94]
_calls = itertools.count()
_lock = threading.Lock()


def _next_signal() -> int:
    with _lock:
        return SEQUENCE[min(next(_calls), len(SEQUENCE) - 1)]


@app.get("/ping")
def ping() -> dict:
    signal_strength = _next_signal()
    if signal_strength < 40:
        message = "static"
    elif signal_strength < 80:
        message = "signal acquired"
    else:
        message = "channel open"
    # Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
    stardate = round(78000.0 + (int(time.time()) - 1767225600) / 3600.0, 1)
    logger.info("subspace-beacon answered ping signalStrength=%d", signal_strength)
    return {
        "beaconId": "relay-theta-9",
        "signalStrength": signal_strength,
        "message": message,
        "stardate": stardate,
    }
