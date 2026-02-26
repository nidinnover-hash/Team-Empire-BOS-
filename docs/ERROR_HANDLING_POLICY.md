# Error Handling Policy

This policy defines where broad exception handling is allowed and where it is not.

## Goals
- Prevent silent failures in core business logic.
- Keep background/best-effort flows resilient.
- Make failures visible with structured logs and tests.

## Rules
1. Use typed exceptions in core paths.
- Prefer `ValueError`, `TypeError`, `SQLAlchemyError`, and domain-specific errors.
- Avoid `except Exception` in CRUD, validation, parsing, and auth logic.

2. Broad catch is allowed only at explicit boundaries.
- Boundary examples: scheduler loops, optional integrations, background tasks, non-critical context enrichment.
- If using `except Exception` in async code, always handle cancellation first:
```python
except asyncio.CancelledError:
    raise
except Exception as exc:
    ...
```

3. Never swallow silently.
- Every catch block must either:
  - re-raise, or
  - log with context (`org_id`, integration/provider, error type), or
  - return a typed fallback object.

4. Rollback only for DB failures.
- In transaction paths, catch `SQLAlchemyError`, rollback, then raise.

5. Preserve external resilience.
- Integration fetch/sync flows may be best-effort, but must:
  - log the failure type
  - continue with other integrations
  - update health/status markers when possible

## Review Checklist (PR)
- Is there any new `except Exception`?
- If yes, is it a boundary?
- If async, does it re-raise `CancelledError` first?
- Are logs actionable and non-sensitive?
- Are tests covering failure behavior?

## Commands
- Find broad handlers:
```powershell
rg -n "except Exception" app
```
- Run critical type checks:
```powershell
python -m mypy app/main.py app/services/memory.py app/services/sync_scheduler.py app/services/github_service.py
```
