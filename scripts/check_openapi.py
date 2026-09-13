"""Exit 1 when contracts/openapi.json differs from the runtime OpenAPI document."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.export_openapi import OPENAPI_PATH, render_openapi  # noqa: E402


def main() -> int:
    if not OPENAPI_PATH.exists():
        print("contracts/openapi.json missing — run: uv run python scripts/export_openapi.py")
        return 1
    if OPENAPI_PATH.read_text(encoding="utf-8") != render_openapi():
        print("contracts/openapi.json is stale — run: uv run python scripts/export_openapi.py")
        return 1
    print("contracts/openapi.json matches runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
