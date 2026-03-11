"""CEO Control endpoints — split into sub-modules for maintainability."""
from fastapi import APIRouter

from .brain import router as brain_router
from .ceo import router as ceo_router
from .compliance import router as compliance_router
from .dead_letter import router as dead_letter_router
from .github_maps import router as github_maps_router
from .health import router as health_router
from .jobs import router as jobs_router
from .platform import router as platform_router
from .levers import router as levers_router
from .recruitment import router as recruitment_router

router = APIRouter(prefix="/control", tags=["CEO Control"])
router.include_router(health_router)
router.include_router(compliance_router)
router.include_router(github_maps_router)
router.include_router(jobs_router)
router.include_router(brain_router)
router.include_router(ceo_router)
router.include_router(platform_router)
router.include_router(dead_letter_router)
router.include_router(recruitment_router)
router.include_router(levers_router)
