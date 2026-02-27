# Nidin Nover AI — Operating Guide

## Purpose
AI agent platform for autonomous work operations — task orchestration, multi-integration management, and intelligent decision support with human-in-the-loop safety controls.

## Architecture Rules
- Keep integrations in `app/tools`.
- Keep memory logic in `app/memory`.
- Keep planning/execution logic in `app/agents`.
- Keep audit and safety logic in `app/logs`.

## Safety
- High-risk actions must require explicit human approval.
- Every write/action should generate an audit event.
- Secrets must come from `.env`.

## Current Focus
- Week 1: Auth + RBAC baseline, Projects/Tasks, event logging.
- Preserve existing personal dashboard routes while adding protected ops routes.
