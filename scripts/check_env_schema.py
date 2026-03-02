from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

BOOLEAN_KEYS = {
    "DEBUG",
    "ENFORCE_STARTUP_VALIDATION",
    "COOKIE_SECURE",
    "DB_SCHEMA_ENFORCE_HEAD",
    "AUTO_CREATE_SCHEMA",
    "AUTO_SEED_DEFAULTS",
    "ACCOUNT_MFA_REQUIRED",
    "ACCOUNT_SSO_REQUIRED",
}

BOOLEAN_VALUES = {"true", "false", "1", "0", "yes", "no", "on", "off"}


def _parse_env(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    duplicates: list[str] = []
    if not path.exists():
        return values, duplicates
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if key in values:
            duplicates.append(key)
        values[key] = value.strip()
    return values, duplicates


def main() -> int:
    values, duplicates = _parse_env(ENV_PATH)
    failures: list[str] = []
    if duplicates:
        failures.append("Duplicate .env keys detected: " + ", ".join(sorted(set(duplicates))))
    for key in BOOLEAN_KEYS:
        if key not in values:
            continue
        value = values[key].strip().strip('"').strip("'").lower()
        if value not in BOOLEAN_VALUES:
            failures.append(f"{key} must be boolean-like, found {values[key]!r}")
    if failures:
        print(".env schema check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(".env schema check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
