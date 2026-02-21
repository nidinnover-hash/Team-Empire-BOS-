from fastapi import APIRouter
from app.api.v1.endpoints import (
    health,
    commands,
    tasks,
    notes,
    projects,
    goals,
    contacts,
    finance,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(commands.router)
api_router.include_router(tasks.router)
api_router.include_router(notes.router)
api_router.include_router(projects.router)
api_router.include_router(goals.router)
api_router.include_router(contacts.router)
api_router.include_router(finance.router)
