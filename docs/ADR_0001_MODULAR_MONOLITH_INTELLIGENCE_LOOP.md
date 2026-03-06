# ADR 0001: Modular Monolith Organized Around the Intelligence Loop

Date: 2026-03-06
Status: Accepted

## Context

Nidin BOS has grown into a large modular-monolith with:

- FastAPI transport layers for API and web
- a large `app/services` directory
- many domain models and schemas
- multi-provider AI routing
- approvals and controlled execution
- workflow automation
- multi-org and workspace scoping
- broad integrations and observability

The system is successful in scope, but the internal structure has become hard to reason about. The current problem is not feature absence; it is architectural clarity and maintainability.

The system will remain a modular monolith for now. It is internal-first, with possible SaaS expansion later.

## Decision

Nidin BOS will be reorganized around a single core loop:

`Signal -> Decision -> Execution -> Intelligence`

All major workflows should be explainable in terms of:

1. what signal entered the system,
2. what decision was made,
3. what execution happened,
4. what intelligence or learning was produced.

## Architectural Layers

The target architecture is:

1. `api/` and `web/`
   - transport only
   - request parsing, auth dependencies, response mapping

2. `application/`
   - use-case orchestration
   - transaction boundaries
   - composition across domains and engines

3. `domains/`
   - business capabilities and invariants
   - domain services and repositories
   - domain events/signals

4. `engines/`
   - cross-domain intelligence and control systems
   - Brain Engine
   - Decision Engine
   - Execution Engine
   - Intelligence Engine

5. `platform/`
   - cross-cutting runtime and infrastructure abstractions
   - signals, policy, audit, tenancy, telemetry, config, idempotency

6. `adapters/`
   - external provider and infrastructure integrations
   - AI providers
   - SaaS/API integrations
   - storage/messaging transports

## Engine Definitions

### Brain Engine

Purpose:
- transform intent + context + policy into structured proposals

Allowed:
- AI routing
- context assembly
- model selection
- confidence scoring
- structured proposal extraction

Not allowed:
- direct world mutations
- direct provider side effects
- bypassing domain or execution rules

### Decision Engine

Purpose:
- evaluate whether a proposed or triggered action should proceed

Allowed:
- policy evaluation
- risk classification
- approval resolution
- automation planning
- creation of decision records and execution plans

Not allowed:
- raw provider calls
- ad hoc state mutation outside domain/application paths

### Execution Engine

Purpose:
- safely run approved actions through typed handlers

Allowed:
- idempotent execution
- action validation
- retries
- execution journaling
- signal emission

Not allowed:
- policy ownership
- AI reasoning ownership

### Intelligence Engine

Purpose:
- turn accumulated activity into insights, projections, and learnings

Allowed:
- aggregation
- trend analysis
- projections for dashboards
- learning feedback
- pattern detection

Not allowed:
- hidden operational side effects

## Signal System

The platform will converge on a unified internal signal model. Signals are the common language between integrations, domains, engines, and projections.

The signal envelope should include:

- id
- type
- category
- org/workspace scope
- actor
- source
- subject
- timestamps
- correlation/causation ids
- payload
- metadata

Signals are the backbone for:

- decision triggers
- observability
- execution journaling
- dashboard projections
- learning feedback

## Migration Rules

These rules apply immediately for all new code.

### Transport rules

`app/api` and `app/web` may:
- validate input
- apply auth/deps
- call application services
- map responses

They may not:
- contain business workflows
- call providers directly
- contain AI orchestration

### Domain rules

`domains/*` may:
- enforce domain invariants
- own domain state
- emit domain signals

They may not:
- call AI providers directly
- perform unrelated cross-domain orchestration
- shape transport responses

### Application rules

`application/*` may:
- orchestrate use cases
- define transaction boundaries
- compose domains and engines

They may not:
- own raw provider adapters
- become a new generic dumping ground

### Adapter rules

`adapters/*` may:
- speak external protocols
- normalize external responses
- handle auth/refresh mechanics

They may not:
- make business decisions
- contain approval policy

### Engine rules

`engines/*` may:
- reason across domains
- produce proposals, decisions, plans, insights

They may not:
- bypass typed execution
- bypass domain invariants

## Immediate Practical Guidance

The current `app/services` directory remains in place temporarily. It should be treated as a compatibility layer during migration, not as the target architecture.

Effective immediately:

- new cross-domain orchestration goes into `application/`
- new domain logic goes into `domains/`
- new AI/decision/execution/intelligence logic goes into `engines/`
- new provider code goes into `adapters/`
- new platform primitives go into `platform/`

## Consequences

### Positive

- clearer ownership boundaries
- easier reasoning about side effects
- better support for solo maintenance
- easier future extraction of async workers
- reduced growth pressure on `app/services`

### Negative

- temporary duplication during migration
- wrapper modules will exist for some time
- initial refactor cost before simplification benefits fully land

## Follow-up

Next concrete steps:

1. create package skeletons for the new architecture
2. extract Brain Engine package with compatibility wrappers
3. introduce the Signal system in `platform/signals`
4. extract Decision Engine
5. extract Execution Engine
6. gradually reclassify `app/services/*`
