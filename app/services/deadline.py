"""Overall request deadline + remaining-budget propagation to per-stage model calls.

`with_deadline` is the outer bound (asyncio cancellation of whatever is in flight). While it is
active it also publishes the absolute deadline in a ContextVar so each stage can cap its own
timeout at the REMAINING budget (`budget_spec`). Stage timeouts (observe/synthesis/repair) are
therefore upper bounds, not reservations: observe 60 + synthesis 90 + repair 40 = 190 s can never
run past the 180 s request deadline, and a stage that cannot get a useful slice is not started.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any

from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.gemini.gateway import GenerationSpec

log = logging.getLogger("sosu.deadline")

# Safety margin kept free before the outer deadline, and the smallest slice worth starting a model
# call with. Both scale with the deadline (5 % / 10 %) so tiny test deadlines behave like 180 s:
# at 180 s → margin 2 s, minimum 3 s.
SAFETY_MARGIN_SECONDS = 2.0
MIN_STAGE_SECONDS = 3.0
_MARGIN_FRACTION = 0.05
_MIN_STAGE_FRACTION = 0.10

_TIMEOUT_MESSAGE = "AI 처리 시간이 허용 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."


@dataclass(frozen=True, slots=True)
class _Budget:
    deadline_at: float  # loop.time() at which the outer deadline fires
    total_seconds: float

    @property
    def margin(self) -> float:
        return min(SAFETY_MARGIN_SECONDS, self.total_seconds * _MARGIN_FRACTION)

    @property
    def min_stage(self) -> float:
        return min(MIN_STAGE_SECONDS, self.total_seconds * _MIN_STAGE_FRACTION)


_BUDGET: ContextVar[_Budget | None] = ContextVar("sosu_request_budget", default=None)


async def with_deadline[T](coro: Coroutine[Any, Any, T], *, seconds: float, request_id: str) -> T:
    loop = asyncio.get_running_loop()
    token = _BUDGET.set(_Budget(deadline_at=loop.time() + seconds, total_seconds=seconds))
    try:
        async with asyncio.timeout(seconds):
            return await coro
    except TimeoutError:
        log.warning("request deadline exceeded request_id=%s deadline=%ss", request_id, seconds)
        raise SosuError(
            ErrorCode.MODEL_TIMEOUT,
            _TIMEOUT_MESSAGE,
            details=[{"deadline_seconds": seconds}],
        ) from None
    finally:
        _BUDGET.reset(token)


def remaining_seconds() -> float | None:
    """Seconds left before the active request deadline, or None outside `with_deadline`."""
    budget = _BUDGET.get()
    if budget is None:
        return None
    return budget.deadline_at - asyncio.get_running_loop().time()


def stage_timeout(stage_seconds: float, *, stage: str) -> float:
    """min(stage_seconds, remaining − margin). Raises MODEL_TIMEOUT if too little budget is left."""
    budget = _BUDGET.get()
    if budget is None:
        return stage_seconds
    remaining = budget.deadline_at - asyncio.get_running_loop().time()
    usable = remaining - budget.margin
    if usable < budget.min_stage:
        log.warning(
            "request budget exhausted before stage=%s remaining=%.3fs deadline=%ss",
            stage,
            remaining,
            budget.total_seconds,
        )
        raise SosuError(
            ErrorCode.MODEL_TIMEOUT,
            _TIMEOUT_MESSAGE,
            details=[{"deadline_seconds": budget.total_seconds, "stage": stage}],
        )
    return min(stage_seconds, usable)


def budget_spec(spec: GenerationSpec) -> GenerationSpec:
    """Return `spec` with its timeout capped by the remaining request budget."""
    timeout = stage_timeout(spec.timeout_seconds, stage=spec.prompt_version)
    if timeout == spec.timeout_seconds:
        return spec
    return replace(spec, timeout_seconds=timeout)
