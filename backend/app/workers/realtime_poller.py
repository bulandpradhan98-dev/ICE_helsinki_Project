from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.database import get_pool
from app.jobs.gtfs_rt_poller import poll_and_store_realtime

logger = logging.getLogger("transit.realtime_poller")


async def run_forever() -> None:
    settings = get_settings()
    interval_seconds = max(settings.gtfs_rt_poll_interval_seconds, 5)

    # Create the DB pool early so connection errors surface before the loop begins.
    await get_pool()
    logger.info(
        "Starting GTFS-RT polling worker for %s (%s) every %s seconds.",
        settings.city_name,
        settings.agency_name,
        interval_seconds,
    )

    while True:
        try:
            details = await poll_and_store_realtime()
            logger.info(
                "Stored GTFS-RT snapshot: %s vehicle positions, %s trip updates.",
                details.get("vehicle_positions", 0),
                details.get("trip_updates", 0),
            )
        except Exception:
            logger.exception("Automatic GTFS-RT polling failed.")

        await asyncio.sleep(interval_seconds)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
