from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import format_startup_issues, settings, validate_startup_settings


def _prod_like_settings():
    return settings.model_copy(
        update={
            "DEBUG": False,
            "ENFORCE_STARTUP_VALIDATION": True,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check production-like startup config.")
    parser.add_argument(
        "--import-app",
        action="store_true",
        help="Also import app.main after config validation passes.",
    )
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="Allow sqlite DATABASE_URL for local dry-runs (non-release).",
    )
    args = parser.parse_args()

    effective = _prod_like_settings()
    issues = validate_startup_settings(effective)
    if args.allow_sqlite:
        issues = [i for i in issues if "DATABASE_URL should not use sqlite when DEBUG=false" not in i]
    if issues:
        print("Production-like startup validation failed:")
        print(format_startup_issues(issues))
        return 1

    print("Production-like startup validation passed.")

    if args.import_app:
        import app.main  # noqa: F401

        print("Imported app.main successfully.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
