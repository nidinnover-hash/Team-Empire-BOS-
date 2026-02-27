from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _must_contain(path: Path, snippets: list[str], failures: list[str]) -> None:
    if not path.exists():
        failures.append(f"Missing required file: {path.relative_to(ROOT)}")
        return
    content = path.read_text(encoding="utf-8", errors="ignore")
    for snippet in snippets:
        if snippet not in content:
            failures.append(f"{path.relative_to(ROOT)} missing required text: {snippet!r}")


def main() -> int:
    failures: list[str] = []

    _must_contain(
        ROOT / "docs" / "SLO_ERROR_BUDGET.md",
        ["99.9%", "Error budget", "p95"],
        failures,
    )
    _must_contain(
        ROOT / "docs" / "INCIDENT_RESPONSE_PLAYBOOK.md",
        ["First 15 minutes", "Severity levels", "Postmortem"],
        failures,
    )
    _must_contain(
        ROOT / "docs" / "BACKUP_RESTORE_DRILL.md",
        ["RTO", "RPO", "/api/v1/control/backup"],
        failures,
    )
    _must_contain(
        ROOT / "docs" / "PRODUCTION_RUNBOOK.md",
        ["Rollback", "Credential rotation", "Incident response priorities"],
        failures,
    )

    if failures:
        print("Ops readiness check failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("Ops readiness check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
