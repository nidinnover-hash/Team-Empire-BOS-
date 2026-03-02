from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sdk" / "openapi" / "openapi.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.main import app

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Avoid lifespan startup side effects during SDK schema export.
    client = TestClient(app)
    response = client.get("/openapi.json")
    response.raise_for_status()
    OUT.write_text(json.dumps(response.json(), indent=2, ensure_ascii=True), encoding="utf-8")
    sys.stdout.write(f"Exported OpenAPI schema to {OUT}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
