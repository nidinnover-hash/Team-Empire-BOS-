## Summary
- 

## ClickUp Task
- Primary Task ID: CU-____
- Related Task IDs (optional): 

## Type of Change
- [ ] Feature
- [ ] Bug fix
- [ ] Refactor
- [ ] Docs
- [ ] Tests

## Validation
- [ ] `py -3.12 scripts/dev_gate.py`
- [ ] `py -3.12 scripts/check_ready.py`
- [ ] `ruff check app tests`
- [ ] `python -m mypy app tests`
- [ ] `python -m pytest -q -p no:cacheprovider`
- [ ] `python scripts/check_migration_heads.py`
- [ ] `pip-audit -r requirements.txt --progress-spinner off`
- [ ] `bandit -r app -ll -q`

## Release Safety
- [ ] No new secrets in logs/responses
- [ ] Privacy profile behavior validated (`strict`/`balanced`/`debug`)
- [ ] Rollback path documented for schema or behavior changes
- [ ] Migration impact reviewed (revision chain / downgrade implications)
- [ ] SDK version + `sdk/CHANGELOG.md` updated for API/OpenAPI contract changes

## Notes for Reviewers
- 
