# Personal AI Clone Operating Guide

## Purpose
This repository implements Phase 1 (Me First): personal work automation with a controlled dashboard interface.

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
