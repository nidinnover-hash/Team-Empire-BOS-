"""Study abroad (ESA) — application milestones and risk status. BOS is the control plane."""

from __future__ import annotations

# Stub: no application model yet. Returns contract shape for integration.


async def next_required_steps(organization_id: int, application_id: str) -> dict:
    """Return next required steps for an application. Stub returns empty list."""
    return {"application_id": application_id, "steps": [], "deadline": None}


async def risk_status(organization_id: int, application_id: str) -> dict:
    """Return risk status for an application. Stub returns on_track."""
    return {
        "application_id": application_id,
        "status": "on_track",
        "message": None,
        "critical_deadlines": [],
    }
