import itertools
import logging
import random
import time

from fastapi import FastAPI, Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engineering")


# One warp core reading. Fields are snake_case in Python and camelCase in JSON
# (reading_id <-> readingId). The field order is the JSON key order.
class WarpCoreReading(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True)

    reading_id: str
    stardate: float
    core_temp_k: int
    plasma_flow: float


# Per-process counter, so the first reading is wc-0001.
_counter = itertools.count(1)


def create_reading() -> WarpCoreReading:
    # Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
    stardate = round(78000.0 + (int(time.time()) - 1767225600) / 3600.0, 1)
    return WarpCoreReading(
        reading_id=f"wc-{next(_counter):04d}",
        stardate=stardate,
        core_temp_k=random.randint(850, 950),
        plasma_flow=random.randint(70, 100) / 100,
    )


app = FastAPI()


# An input binding needs no Dapr code at all: the sidecar calls a plain HTTP endpoint whose
# path is the component name (warp-core-scan). No decorator, no Dapr package.
@app.post("/warp-core-scan")
async def warp_core_scan() -> Response:
    reading = create_reading()
    logger.info(
        "engineering warp-core scan %s stardate=%.1f coreTempK=%d plasmaFlow=%.2f",
        reading.reading_id,
        reading.stardate,
        reading.core_temp_k,
        reading.plasma_flow,
    )
    # Any 2xx tells Dapr the tick was handled.
    return Response(status_code=200)
