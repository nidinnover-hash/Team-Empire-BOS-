from __future__ import annotations

import sys

REQUIRED_MAJOR = 3
REQUIRED_MINOR = 12


def main() -> int:
    current = (sys.version_info.major, sys.version_info.minor)
    required = (REQUIRED_MAJOR, REQUIRED_MINOR)
    if current == required:
        print(f"Python preflight passed ({current[0]}.{current[1]}).")
        return 0
    print(
        "Python preflight failed: "
        f"required {required[0]}.{required[1]}, detected {current[0]}.{current[1]}."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
