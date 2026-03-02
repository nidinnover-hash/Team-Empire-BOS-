from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv312",
    "node_modules",
    "strategy-pack",
    "test-results",
    "tests",
}

BLOCKED_FILE_PATTERNS = [
    re.compile(r"^client_secret_.*\.googleusercontent\.com\.json$", re.IGNORECASE),
]

BLOCKED_CONTENT_PATTERNS = [
    re.compile(r'"client_secret"\s*:\s*"[^"]{8,}"', re.IGNORECASE),
    re.compile(r'"private_key"\s*:\s*"-----BEGIN PRIVATE KEY-----', re.IGNORECASE),
]

TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".ini",
    ".toml",
    ".env",
    ".ps1",
    ".sh",
    ".js",
    ".ts",
    ".html",
    ".css",
}


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if _is_excluded(path.relative_to(ROOT)):
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower().startswith(".env"):
            files.append(path)
    return files


def main() -> int:
    failures: list[str] = []
    files = _candidate_files()
    for file_path in files:
        rel = file_path.relative_to(ROOT)
        name = rel.name
        if any(pattern.match(name) for pattern in BLOCKED_FILE_PATTERNS):
            failures.append(f"Blocked secret filename detected: {rel}")
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in BLOCKED_CONTENT_PATTERNS:
            if pattern.search(content):
                failures.append(f"Potential secret detected in {rel}: pattern={pattern.pattern}")
                break

    if failures:
        print("Secret pattern guard failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Secret pattern guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
