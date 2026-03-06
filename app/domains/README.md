# Domain Modules

This package owns business capabilities and invariants.

Each domain module should be narrow and explicit. Typical contents:

- `service.py` for domain operations
- `repo.py` for persistence access
- `events.py` for emitted domain signals

Examples:

- tasks
- projects
- contacts
- approvals
- workspaces
- organizations
- memory

Domain modules should not call AI providers directly or perform unrelated cross-domain orchestration.
