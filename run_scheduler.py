"""
Standalone scheduler process for production.

Run as a separate systemd service so Gunicorn workers only handle HTTP.
Usage: python run_scheduler.py
"""
import asyncio
import logging
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("scheduler")


async def main() -> None:
    from app.core.config import settings
    from app.db.session import engine
    from app.services.sync_scheduler import _scheduler_loop

    interval = settings.SYNC_INTERVAL_MINUTES
    logger.info("Starting standalone scheduler (interval=%d min)", interval)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _shutdown(sig: signal.Signals) -> None:
        logger.info("Received %s, shutting down...", sig.name)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig)

    task = asyncio.create_task(_scheduler_loop(interval))
    await stop.wait()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await engine.dispose()
    logger.info("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
