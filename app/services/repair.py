"""validate → (one repair call at most) → validate. No loops, no recursion."""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel

from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.domain.validator import ValidationOutcome, ValidationReport
from app.gemini.gateway import GeminiGateway, GenerationSpec

log = logging.getLogger("sosu.repair")


async def run_with_repair[T: BaseModel](
    *,
    gateway: GeminiGateway,
    spec_repair: GenerationSpec,
    draft: T,
    validate: Callable[[T], ValidationReport],
    build_repair_prompt: Callable[[T, list[str]], tuple[str, str]],
    schema: type[T],
    request_id: str,
) -> T:
    report = validate(draft)
    if report.outcome is ValidationOutcome.PASS:
        log.info("validation request_id=%s outcome=PASS", request_id)
        return draft
    if report.outcome is ValidationOutcome.FATAL:
        log.warning(
            "validation request_id=%s outcome=FATAL errors=%d", request_id, len(report.errors)
        )
        raise SosuError(
            ErrorCode.MODEL_CONTENT_ERROR,
            "Model output was not usable.",
            details=report.errors[:10],
        )

    log.info(
        "validation request_id=%s outcome=REPAIRABLE errors=%d -> repair once",
        request_id,
        len(report.errors),
    )
    system, user = build_repair_prompt(draft, report.errors)
    repaired = await gateway.generate_structured(
        spec=spec_repair,
        system_instruction=system,
        user_text=user,
        images=[],
        schema=schema,
    )
    second = validate(repaired.value)
    if second.outcome is ValidationOutcome.PASS:
        log.info("validation request_id=%s outcome=PASS (after repair)", request_id)
        return repaired.value

    log.warning(
        "validation request_id=%s outcome=%s after repair errors=%d",
        request_id,
        second.outcome,
        len(second.errors),
    )
    raise SosuError(
        ErrorCode.REPAIR_FAILED,
        "Model output could not be repaired to satisfy the contract.",
        details=second.errors[:10],
    )
