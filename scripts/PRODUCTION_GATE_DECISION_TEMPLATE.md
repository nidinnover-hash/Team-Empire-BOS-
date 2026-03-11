# Production Gate Decision Template

## 1. Inputs Reviewed
- Staging gate report: `STAGING_GATE_REPORT.md`
- Alembic outputs: `current`, `heads`, `upgrade #1`, `upgrade #2`
- Seed output: `scripts/seed_staging_users.py`
- SQL checks: A-F

## 2. Staging Operational Verdict
- Verdict: `PASS | FAIL`
- Summary:
  - 

## 3. Rollback Trigger Check
- Rollback triggers present: `YES | NO`
- Evidence:
  - 

## 4. Migration Integrity
- `alembic_version` row count = `1`: `YES | NO`
- `current == heads`: `YES | NO`
- First upgrade succeeded: `YES | NO`
- Second upgrade no-op succeeded: `YES | NO`
- Drift indicators present: `YES | NO`

## 5. Safety Areas
- Tenant isolation: `PASS | FAIL`
- Audit correctness: `PASS | FAIL`
- Audit duplication risk acceptable: `YES | NO`
- Protected field immutability: `PASS | FAIL`
- Quote approval pending-only guard: `PASS | FAIL`
- Forecast/conversion upsert idempotency: `PASS | FAIL`
- Automation template endpoints: `PASS | FAIL`

## 6. Production Decision
- Production allowed: `YES | NO`
- Confidence score: `__/100`

## 7. Remaining Blockers
1. 
2. 
3. 

## 8. Required Evidence to Close Blockers
1. 
2. 
3. 

