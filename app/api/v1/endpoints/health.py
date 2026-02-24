import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import engine
from app.schemas.health import HealthCheckResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Returns API status and confirms the database is reachable (pool-independent)."""
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3.0)
        db_status = "ok"
    except Exception as exc:
        logger.warning("DB health check failed: %s", exc)
        db_status = "unreachable"
    payload = {"status": "ok" if db_status == "ok" else "degraded", "database": db_status}
    return JSONResponse(content=payload, status_code=200 if db_status == "ok" else 503)
