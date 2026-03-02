from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    "sdk/python/nidin_bos_sdk/client.py",
    "sdk/typescript/src/client.ts",
]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def main() -> int:
    gen = _run([sys.executable, "scripts/generate_sdk_clients.py"])
    if gen.returncode != 0:
        sys.stderr.write(gen.stdout)
        sys.stderr.write(gen.stderr)
        return gen.returncode

    diff = _run(["git", "diff", "--exit-code", "--", *TARGETS])
    if diff.returncode != 0:
        sys.stderr.write("SDK client generation drift detected. Re-run generate_sdk_clients.py and commit.\n")
        sys.stderr.write(diff.stdout)
        sys.stderr.write(diff.stderr)
        return 1

    sys.stdout.write("SDK client generation parity check passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
