from __future__ import annotations

from scripts.pr_checklist_guard import evaluate_pr_checklist


def test_pr_checklist_requires_dev_or_ready() -> None:
    failures = evaluate_pr_checklist(body="- [ ] nothing", paths=[])
    assert any("scripts/dev_gate.py" in failure for failure in failures)


def test_pr_checklist_migration_ack_required_when_models_change() -> None:
    body = "- [x] `py -3.12 scripts/dev_gate.py`"
    paths = ["app/models/task.py"]
    failures = evaluate_pr_checklist(body=body, paths=paths)
    assert any("Migration/model changes detected" in failure for failure in failures)


def test_pr_checklist_sdk_ack_required_when_contract_changes() -> None:
    body = "- [x] `py -3.12 scripts/check_ready.py`"
    paths = ["app/api/v1/endpoints/tasks.py"]
    failures = evaluate_pr_checklist(body=body, paths=paths)
    assert any("API/OpenAPI contract changes detected" in failure for failure in failures)


def test_pr_checklist_passes_when_required_checks_are_marked() -> None:
    body = "\n".join(
        [
            "- [x] `py -3.12 scripts/dev_gate.py`",
            "- [x] Migration impact reviewed (revision chain / downgrade implications)",
            "- [x] SDK version + `sdk/CHANGELOG.md` updated for API/OpenAPI contract changes",
        ]
    )
    paths = [
        "alembic/versions/20260302_9999_test.py",
        "app/models/task.py",
        "app/api/v1/endpoints/tasks.py",
    ]
    failures = evaluate_pr_checklist(body=body, paths=paths)
    assert failures == []
