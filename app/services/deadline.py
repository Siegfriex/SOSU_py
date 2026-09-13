"""Overall request deadline. Stage timeouts live on GenerationSpec; this is the outer bound."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError

log = logging.getLogger("sosu.deadline")


async def with_deadline[T](coro: Coroutine[Any, Any, T], *, seconds: float, request_id: str) -> T:
    try:
        async with asyncio.timeout(seconds):
            return await coro
    except TimeoutError:
        log.warning("request deadline exceeded request_id=%s deadline=%ss", request_id, seconds)
        raise SosuError(
            ErrorCode.MODEL_TIMEOUT,
            "AI 처리 시간이 허용 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
            details=[{"deadline_seconds": seconds}],
        ) from None
