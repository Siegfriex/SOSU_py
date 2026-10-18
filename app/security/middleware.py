"""Pure-ASGI guard that runs BEFORE FastAPI reads/parses any request body.

Order for every request:
  1. `X-SOSU-Build` response header (public deployment SHA, or omitted when unknown).
  2. Body size cap (Content-Length, or streamed count when absent) → 413 IMAGE_TOO_LARGE.
  3. AI routes on a public runtime: fail-closed gate → 503 SERVICE_UNAVAILABLE.
  4. AI / e-mail routes on a public runtime: per-instance token bucket → 429 RATE_LIMITED.

Only request_id, path and error code are logged — never bodies, e-mails, images or IPs.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from fastapi.responses import JSONResponse

from app.api.errors import envelope_dict
from app.config import get_settings
from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.security.ratelimit import TokenBucketLimiter
from app.security.runtime import build_sha, inference_status, is_public_runtime

logger = logging.getLogger("sosu.security")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

AI_PATHS = frozenset({"/api/v1/diagnosis", "/api/v1/prescription"})
EMAIL_PATHS = frozenset({"/api/v1/report-email"})

SERVICE_UNAVAILABLE_MESSAGE = (
    "현재 AI 생성 서비스가 일시 중단되어 있습니다. 잠시 후 다시 이용해 주세요."
)
RATE_LIMITED_MESSAGE = "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."
BODY_TOO_LARGE_MESSAGE = "요청 본문이 허용 용량을 초과했습니다."

_SAFE_RID = re.compile(r"[^A-Za-z0-9._-]")


def _header(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k.lower() == name:
            return bytes(v).decode("latin-1")
    return None


def _request_id(scope: Scope) -> str:
    state = scope.get("state") or {}
    rid = state.get("request_id") if isinstance(state, dict) else None
    if rid:
        return str(rid)
    raw = _header(scope, b"x-request-id") or ""
    cleaned = _SAFE_RID.sub("", raw)[:64]
    return cleaned or uuid.uuid4().hex


def _client_key(scope: Scope) -> str:
    fwd = _header(scope, b"x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = _header(scope, b"x-real-ip")
    if real:
        return real.strip()
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


class SecurityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._limiters: dict[tuple[str, int], TokenBucketLimiter] = {}

    def _limiter(self, group: str, per_minute: int) -> TokenBucketLimiter:
        key = (group, per_minute)
        if key not in self._limiters:
            self._limiters[key] = TokenBucketLimiter(per_minute)
        return self._limiters[key]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        sha = build_sha()

        async def send_with_build(message: Message) -> None:
            if sha and message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-sosu-build", sha.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        settings = get_settings()
        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET")).upper()
        public = is_public_runtime(settings)

        async def reject(err: SosuError) -> None:
            rid = _request_id(scope)
            logger.info("request_id=%s path=%s rejected=%s", rid, path, err.code)
            resp = JSONResponse(status_code=err.http_status, content=envelope_dict(err, rid))
            await resp(scope, receive, send_with_build)

        if method == "POST" and path in AI_PATHS:
            enabled, reason = inference_status(settings)
            if not enabled:
                await reject(
                    SosuError(
                        ErrorCode.SERVICE_UNAVAILABLE,
                        SERVICE_UNAVAILABLE_MESSAGE,
                        details=[{"reason": reason}],
                        retryable=False,
                    )
                )
                return

        if method == "POST" and public and (path in AI_PATHS or path in EMAIL_PATHS):
            group = "ai" if path in AI_PATHS else "email"
            per_minute = (
                settings.sosu_ratelimit_ai_per_minute
                if group == "ai"
                else settings.sosu_ratelimit_email_per_minute
            )
            if not self._limiter(group, per_minute).allow(_client_key(scope)):
                await reject(
                    SosuError(
                        ErrorCode.RATE_LIMITED,
                        RATE_LIMITED_MESSAGE,
                        details=[{"scope": "per_instance"}],
                    )
                )
                return

        if method in {"POST", "PUT", "PATCH"}:
            limit = settings.sosu_max_request_bytes
            too_large = SosuError(
                ErrorCode.IMAGE_TOO_LARGE,
                BODY_TOO_LARGE_MESSAGE,
                details=[{"limit_bytes": limit, "field": "request_body"}],
            )
            cl = _header(scope, b"content-length")
            if cl is not None:
                if not cl.strip().isdigit() or int(cl) > limit:
                    await reject(too_large)
                    return
            else:
                # No Content-Length (chunked): buffer up to the cap, then replay.
                messages: list[Message] = []
                total = 0
                while True:
                    msg = await receive()
                    messages.append(msg)
                    if msg["type"] != "http.request":
                        break
                    total += len(msg.get("body", b""))
                    if total > limit:
                        await reject(too_large)
                        return
                    if not msg.get("more_body", False):
                        break
                replay = iter(messages)

                async def replay_receive() -> Message:
                    try:
                        return next(replay)
                    except StopIteration:
                        return await receive()

                await self.app(scope, replay_receive, send_with_build)
                return

        await self.app(scope, receive, send_with_build)
