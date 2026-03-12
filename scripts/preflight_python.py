from __future__ import annotations

import sys

REQUIRED_MAJOR = 3
REQUIRED_MINOR = 12


def main() -> int:
    current = (sys.version_info.major, sys.version_info.minor)
    if current[0] == REQUIRED_MAJOR and current[1] >= REQUIRED_MINOR:
        print(f"Python preflight passed ({current[0]}.{current[1]}).")
        return 0
    print(
        "Python preflight failed: "
        f"required {REQUIRED_MAJOR}.{REQUIRED_MINOR}+, detected {current[0]}.{current[1]}."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
