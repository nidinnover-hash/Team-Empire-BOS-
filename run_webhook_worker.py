from __future__ import annotations

import asyncio
import logging
import os

from app.db.session import AsyncSessionLocal
from app.services.webhook import retry_failed_deliveries

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("webhook_worker")


async def _loop() -> None:
    interval_seconds = int(os.getenv("WEBHOOK_WORKER_INTERVAL_SECONDS", "10"))
    logger.info("Webhook worker started (interval=%ss)", interval_seconds)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                retried = await retry_failed_deliveries(db)
                if retried:
                    logger.info("Webhook worker retried deliveries=%s", retried)
        except Exception:
            logger.exception("Webhook worker loop failure")
        await asyncio.sleep(max(1, interval_seconds))


def main() -> int:
    try:
        asyncio.run(_loop())
    except KeyboardInterrupt:
        logger.info("Webhook worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
