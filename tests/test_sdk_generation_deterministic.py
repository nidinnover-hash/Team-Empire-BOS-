from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_CLIENT = ROOT / "sdk" / "python" / "nidin_bos_sdk" / "client.py"
TS_CLIENT = ROOT / "sdk" / "typescript" / "src" / "client.ts"
GEN_SCRIPT = ROOT / "scripts" / "generate_sdk_clients.py"


def _run_generator() -> None:
    proc = subprocess.run(
        [sys.executable, str(GEN_SCRIPT)],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "generate_sdk_clients.py failed\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )


def test_generated_sdk_clients_are_deterministic() -> None:
    original_py = PY_CLIENT.read_text(encoding="utf-8")
    original_ts = TS_CLIENT.read_text(encoding="utf-8")
    try:
        _run_generator()
        after_first_py = PY_CLIENT.read_text(encoding="utf-8")
        after_first_ts = TS_CLIENT.read_text(encoding="utf-8")

        _run_generator()
        after_second_py = PY_CLIENT.read_text(encoding="utf-8")
        after_second_ts = TS_CLIENT.read_text(encoding="utf-8")
    finally:
        PY_CLIENT.write_text(original_py, encoding="utf-8")
        TS_CLIENT.write_text(original_ts, encoding="utf-8")

    assert after_first_py == after_second_py
    assert after_first_ts == after_second_ts
