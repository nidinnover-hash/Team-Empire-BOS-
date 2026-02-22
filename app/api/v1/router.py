from fastapi import APIRouter
from app.api.v1.endpoints import (
    agents,
    approvals,
    auth,
    briefing,
    email,
    health,
    commands,
    tasks,
    notes,
    projects,
    goals,
    contacts,
    executions,
    finance,
    integrations,
    memory,
    ops,
    orgs,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(approvals.router)
api_router.include_router(agents.router)
api_router.include_router(memory.router)
api_router.include_router(briefing.router)
api_router.include_router(email.router)
api_router.include_router(orgs.router)
api_router.include_router(commands.router)
api_router.include_router(tasks.router)
api_router.include_router(notes.router)
api_router.include_router(projects.router)
api_router.include_router(goals.router)
api_router.include_router(contacts.router)
api_router.include_router(executions.router)
api_router.include_router(integrations.router)
api_router.include_router(finance.router)
api_router.include_router(ops.router)
