# Project Context

## Product
Nidin Nover AI — autonomous agent platform for work operations.

## Phase
Phase 1: Me First (personal dashboard, task/notes/projects workflows).

## Backend
- FastAPI
- Async SQLAlchemy
- SQLite now, Postgres/Supabase target

## New Week-1 Architecture Additions
- RBAC helper (`app/core/rbac.py`)
- Ops endpoints (`/api/v1/ops/*`)
- Event log model/service for audit trail
- Reserved folders: `app/agents`, `app/memory`, `app/tools`, `app/logs`
