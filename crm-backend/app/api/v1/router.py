from fastapi import APIRouter

from app.api.v1.endpoints import health

api_router = APIRouter()

api_router.include_router(health.router)

# ── Add feature routers here as you build them ────────────────────────────────
# from app.api.v1.endpoints import leads, auth
# api_router.include_router(leads.router,  prefix="/leads",  tags=["Leads"])
# api_router.include_router(auth.router,   prefix="/auth",   tags=["Auth"])
