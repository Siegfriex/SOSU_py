"""DEV/TEST ONLY — run the real SOSU API with a deterministic fake Gemini gateway.

    cd SOSU_py && .venv/bin/python scripts/serve_fake.py --port 8000

What is real: routing, multipart parsing, request/image validation, sufficiency, evidence pack,
prompt building (incl. guidebook knowledge), semantic validator, repair loop, error envelope.
What is fake: only the GeminiGateway (scripts/fake_gateway.py). All model output is TEST DATA.

Extra routes (exist ONLY in this app, never in `app.main.create_app()`):
    GET  /__fake__/scenario                 current queue state
    POST /__fake__/scenario                 {"scenario": str, "times": int=1, "delay_s": float?}
    POST /__fake__/reset                    clear scenario queue + captured requests
    GET  /__fake__/last-request[?all=1]     last (or last 20) captured generation requests
Per-request override header: `X-SOSU-Fake-Scenario: <name>` or `slow:<seconds>`.
Every response carries `X-SOSU-Fake: 1`.

Binds to 127.0.0.1 only. Refuses to start when SOSU_ENV=production.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # `python scripts/serve_fake.py` → make `app`/`scripts` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from scripts.fake_gateway import (
    SCENARIOS,
    ScenarioController,
    ScenarioFakeGateway,
    parse_scenario_header,
)

DEV_CORS_ORIGINS = (
    "http://localhost:5197",
    "http://127.0.0.1:5197",
    "http://localhost:5199",
    "http://127.0.0.1:5199",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
CAPTURED_PATHS = frozenset({"/api/v1/diagnosis", "/api/v1/prescription"})
CAPTURE_KEEP = 20
FAKE_BANNER = "FAKE GATEWAY — TEST DATA (scripts/serve_fake.py; not for production)"


class ScenarioBody(BaseModel):
    scenario: str
    times: int = Field(default=1, ge=0, le=1000)
    delay_s: float | None = Field(default=None, ge=0, le=170)


class FakeState:
    def __init__(self) -> None:
        self.controller = ScenarioController()
        self.gateway = ScenarioFakeGateway(controller=self.controller)
        self.captured: deque[dict[str, Any]] = deque(maxlen=CAPTURE_KEEP)


async def _capture(scope: Scope, body: bytes, request_id: str | None) -> dict[str, Any]:
    async def replay() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    req = Request(scope, replay)
    record: dict[str, Any] = {
        "endpoint": scope["path"],
        "request_id": request_id,
        "content_type": req.headers.get("content-type"),
        "payload": None,
        "payload_raw": None,
        "files": [],
        "received_at": datetime.now(UTC).isoformat(),
    }
    try:
        form = await req.form(max_files=50, max_fields=50)
    except Exception as exc:  # malformed multipart is still useful to report
        record["parse_error"] = type(exc).__name__
        return record

    for key, value in form.multi_items():
        if isinstance(value, UploadFile):
            data = await value.read()
            record["files"].append(
                {
                    "field": key,
                    "filename": value.filename,
                    "content_type": value.content_type,
                    "size_bytes": len(data),
                }
            )
        elif key == "payload":
            record["payload_raw"] = value if len(value) <= 20_000 else value[:20_000]
            try:
                record["payload"] = json.loads(value)
            except ValueError:
                record["payload"] = None
    await form.close()
    return record


class FakeMiddleware:
    """Pure ASGI: marks responses, sets per-request scenario contextvar, captures requests."""

    def __init__(self, app: ASGIApp, state: FakeState) -> None:
        self.app = app
        self.state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        token = self.state.controller.begin_request(
            parse_scenario_header(headers.get("x-sosu-fake-scenario"))
        )

        downstream_receive = receive
        if scope["method"] == "POST" and scope["path"] in CAPTURED_PATHS:
            chunks: list[bytes] = []
            more = True
            while more:
                message = await receive()
                if message["type"] == "http.disconnect":
                    break
                chunks.append(message.get("body", b""))
                more = message.get("more_body", False)
            body = b"".join(chunks)
            self.state.captured.append(await _capture(scope, body, headers.get("x-request-id")))
            sent = False

            async def replay_receive() -> Message:
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            downstream_receive = replay_receive

        async def send_marked(message: Message) -> None:
            if message["type"] == "http.response.start":
                hdrs = list(message.get("headers", []))
                hdrs.append((b"x-sosu-fake", b"1"))
                for i, (k, v) in enumerate(hdrs):
                    if k.lower() == b"access-control-expose-headers":
                        hdrs[i] = (k, v + b", X-SOSU-Fake")
                message = {**message, "headers": hdrs}
                if scope["path"] in CAPTURED_PATHS and self.state.captured:
                    for k, v in hdrs:
                        if k.lower() == b"x-request-id":
                            self.state.captured[-1]["request_id"] = v.decode("latin-1")
            await send(message)

        try:
            await self.app(scope, downstream_receive, send_marked)
        finally:
            self.state.controller.end_request(token)


def configure_dev_env() -> None:
    """Must run BEFORE app settings are first loaded (get_settings is lru_cached)."""
    existing = [o.strip() for o in os.environ.get("SOSU_CORS_ORIGINS", "").split(",") if o.strip()]
    merged = list(dict.fromkeys([*existing, *DEV_CORS_ORIGINS]))
    os.environ["SOSU_CORS_ORIGINS"] = ",".join(merged)


def build_fake_app(state: FakeState | None = None) -> FastAPI:
    """Real `create_app()` + fake gateway override + /__fake__ control routes. Dev/test only."""
    import logging

    from app.api.deps import get_gateway
    from app.config import get_settings
    from app.main import create_app

    if get_settings().sosu_env == "production":
        raise RuntimeError("serve_fake refuses to run with SOSU_ENV=production")

    st = state or FakeState()
    app = create_app()
    app.title = "SOSU AI Service (FAKE GATEWAY — TEST DATA)"
    app.dependency_overrides[get_gateway] = lambda: st.gateway
    app.state.fake = st

    @app.get("/__fake__/scenario", include_in_schema=False)
    async def get_scenario() -> dict[str, Any]:
        return st.controller.snapshot()

    @app.post("/__fake__/scenario", include_in_schema=False)
    async def set_scenario(body: ScenarioBody) -> dict[str, Any]:
        if body.scenario not in SCENARIOS:
            from app.contracts.envelope import ErrorCode
            from app.domain.errors import SosuError

            raise SosuError(
                ErrorCode.INVALID_REQUEST,
                f"unknown scenario; expected one of {list(SCENARIOS)}",
            )
        st.controller.set(body.scenario, times=body.times, delay_s=body.delay_s)
        return st.controller.snapshot()

    @app.post("/__fake__/reset", include_in_schema=False)
    async def reset() -> dict[str, Any]:
        st.controller.reset()
        st.captured.clear()
        st.gateway.calls.clear()
        return st.controller.snapshot()

    @app.get("/__fake__/last-request", include_in_schema=False)
    async def last_request(all: bool = Query(default=False)) -> Any:  # noqa: A002
        if all:
            return list(st.captured)
        return st.captured[-1] if st.captured else None

    app.add_middleware(FakeMiddleware, state=st)
    logging.getLogger("sosu.fake").warning(FAKE_BANNER)
    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="SOSU dev server with a fake Gemini gateway.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    configure_dev_env()
    from app.config import get_settings

    get_settings.cache_clear()

    import uvicorn

    app = build_fake_app()
    print(FAKE_BANNER, flush=True)
    print(f"CORS origins: {get_settings().cors_origins_list}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
