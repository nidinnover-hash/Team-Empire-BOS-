"""
Standalone scheduler process for production.

Run as a separate systemd service so Gunicorn workers only handle HTTP.
Usage: python run_scheduler.py
"""
import asyncio
import logging
import os
import signal
import socket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("scheduler")


def _sd_notify(state: str) -> None:
    """Send a notification to systemd (if NOTIFY_SOCKET is set)."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.sendto(state.encode(), addr)
        sock.close()
    except OSError:
        pass


async def _watchdog_loop(interval: float) -> None:
    """Periodically send WATCHDOG=1 to systemd so it knows we're alive."""
    while True:
        _sd_notify("WATCHDOG=1")
        await asyncio.sleep(interval)


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

    # Tell systemd we're ready
    _sd_notify("READY=1")

    task = asyncio.create_task(_scheduler_loop(interval))

    # Watchdog heartbeat every 50s (WatchdogSec=120 in the service file,
    # systemd recommends notifying at half the interval)
    watchdog = asyncio.create_task(_watchdog_loop(50))

    await stop.wait()
    task.cancel()
    watchdog.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    try:
        await watchdog
    except asyncio.CancelledError:
        pass
    _sd_notify("STOPPING=1")
    await engine.dispose()
    logger.info("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
