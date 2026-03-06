# Architecture Conventions

Date: 2026-03-06

This document defines the practical coding conventions for the modular-monolith redesign of Nidin BOS.

It complements:

- `docs/ADR_0001_MODULAR_MONOLITH_INTELLIGENCE_LOOP.md`

The core loop remains:

`Signal -> Decision -> Execution -> Intelligence`

## 1. Package Placement Rules

### `app/api` and `app/web`

Use for:

- request parsing
- response shaping
- dependency injection
- auth and session enforcement

Do not use for:

- multi-step business workflows
- AI orchestration
- provider protocol handling
- approval decision logic

### `app/application`

Use for:

- use-case orchestration
- transaction boundaries
- composing domains and engines
- workflow-level operations exposed to transport layers

Examples:

- handle chat message
- build dashboard view
- run integration sync workflow
- execute approval-to-plan transition

Do not use for:

- direct provider protocol code
- large collections of generic helper functions

### `app/domains`

Use for:

- business capability modules
- domain invariants
- domain-level CRUD and state transitions
- domain signal emission

Examples:

- tasks
- projects
- contacts
- workspaces
- memory
- organizations

Do not use for:

- LLM provider calls
- unrelated cross-domain orchestration
- transport response shaping

### `app/engines`

Use for the four cross-domain engines:

- Brain
- Decision
- Execution
- Intelligence

Use for:

- context assembly
- confidence scoring
- policy and approval evaluation
- execution planning and typed action handling
- projections, trends, and insights

Do not use for:

- raw HTTP provider clients
- ad hoc persistence everywhere

### `app/platform`

Use for:

- signals
- audit
- policy primitives
- tenancy
- telemetry
- idempotency
- config and infra-facing primitives

Do not use for:

- product-specific workflows
- domain-specific business rules

### `app/adapters`

Use for:

- external API clients
- auth refresh/token handling
- payload normalization
- transport-specific error translation

Do not use for:

- approval policy
- business decision making

## 2. New-Code Rules

Effective immediately:

1. No new feature logic should be added to generic `app/services/`.
2. No new external provider calls should be added outside `app/adapters/`.
3. No new AI orchestration should be added outside `app/engines/brain/`.
4. No new approval policy logic should be added outside `app/engines/decision/`.
5. No new non-trivial side effects should bypass the future Execution Engine path.

## 3. Import Direction Rules

Preferred dependency direction:

- transport -> application
- application -> domains and engines
- engines -> domains and platform
- domains -> platform
- adapters -> external systems

Avoid:

- domains importing transport
- adapters importing route modules
- transport importing provider clients directly

## 4. Migration Rules

During migration, legacy files in `app/services/` may remain as compatibility wrappers.

Wrapper rule:

- old module path stays temporarily
- implementation moves to the new target module
- wrapper imports and re-exports the new implementation

This keeps endpoint and test churn manageable.

## 5. Architecture Checklist for New Features

Every major new feature should answer:

1. What signal starts it?
2. What decision is made?
3. What action executes?
4. What intelligence or projection is produced?
5. Which domain owns the underlying state?

If these answers are unclear, the design is not ready.

## 6. Smell List

Treat these as warnings:

- new generic helpers added to `app/services/`
- route handlers orchestrating multiple business workflows
- provider calls mixed into domain logic
- AI calls embedded in domain CRUD
- approval logic duplicated across endpoints
- dashboards performing wide multi-service fan-out directly from transport
- hidden side effects with no journaled execution or signal emission
