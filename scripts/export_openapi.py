"""Export the runtime OpenAPI document to contracts/openapi.json (deterministic)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import create_app  # noqa: E402

OPENAPI_PATH = ROOT / "contracts" / "openapi.json"


def render_openapi() -> str:
    spec = create_app().openapi()
    return json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(render_openapi(), encoding="utf-8")
    print(f"wrote {OPENAPI_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
