import itertools
import logging
import random
import time
from dataclasses import dataclass

from fastapi import FastAPI, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engineering")


# One warp core reading. The field order is the JSON key order.
@dataclass
class WarpCoreReading:
    readingId: str
    stardate: float
    coreTempK: int
    plasmaFlow: float


# Per-process counter, so the first reading is wc-0001.
_counter = itertools.count(1)


def create_reading() -> WarpCoreReading:
    # Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
    stardate = round(78000.0 + (int(time.time()) - 1767225600) / 3600.0, 1)
    return WarpCoreReading(
        readingId=f"wc-{next(_counter):04d}",
        stardate=stardate,
        coreTempK=random.randint(850, 950),
        plasmaFlow=random.randint(70, 100) / 100,
    )


app = FastAPI()


# An input binding needs no Dapr code at all: the sidecar calls a plain HTTP endpoint whose
# path is the component name (warp-core-scan). No decorator, no Dapr package.
@app.post("/warp-core-scan")
async def warp_core_scan() -> Response:
    reading = create_reading()
    logger.info(
        "engineering warp-core scan %s stardate=%.1f coreTempK=%d plasmaFlow=%.2f",
        reading.readingId,
        reading.stardate,
        reading.coreTempK,
        reading.plasmaFlow,
    )
    # Any 2xx tells Dapr the tick was handled.
    return Response(status_code=200)
