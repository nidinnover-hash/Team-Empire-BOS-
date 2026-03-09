"""Automation endpoints — thin router that includes split sub-modules.

Previously 695 lines, now split into:
  - automation_triggers.py    — Trigger CRUD
  - automation_workflows.py   — Workflow v1 (create, start, advance, run)
  - automation_definitions.py — Workflow v2 definitions, runs, copilot, insights, templates
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.automation_definitions import router as definitions_router
from app.api.v1.endpoints.automation_triggers import router as triggers_router
from app.api.v1.endpoints.automation_workflows import router as workflows_router

router = APIRouter()
router.include_router(triggers_router)
router.include_router(workflows_router)
router.include_router(definitions_router)
