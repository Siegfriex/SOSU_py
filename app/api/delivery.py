"""Phase 2 routes: GET /api/v1/features and POST /api/v1/report-email."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.api.deps import get_settings_dep
from app.api.errors import pydantic_error_details
from app.config import Settings
from app.contracts.diagnosis import DiagnosisReportV1
from app.contracts.envelope import (
    ErrorCode,
    ErrorEnvelope,
    FeatureFlag,
    FeaturesResponse,
    ReportEmailRequestV1,
    ReportEmailResultV1,
    SuccessEnvelope,
)
from app.contracts.prescription import PrescriptionReportV1
from app.domain.errors import SosuError
from app.email.provider import EmailDeliveryError, EmailMessage, EmailProvider, get_email_provider
from app.email.render import render_report_email
from app.security.runtime import build_sha, email_status, inference_status
from app.security.tokens import verify_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)

EMAIL_DISABLED_MESSAGE = "현재 리포트 이메일 발송 기능이 비활성화되어 있습니다."
INVALID_TOKEN_MESSAGE = (
    "리포트 확인 정보가 유효하지 않거나 만료되었습니다. 리포트를 다시 생성해 주세요."
)
DELIVERY_FAILED_MESSAGE = "이메일 발송에 실패했습니다. 잠시 후 다시 시도해 주세요."
IMAGE_STORAGE_REASON = "not_implemented: no consent flow, private storage or retention policy"

_IDEMPOTENCY_TTL_SECONDS = 86_400
_IDEMPOTENCY_MAX = 10_000


class _IdempotencyCache:
    """PER-INSTANCE only (Vercel instances do not share memory). Resend's own Idempotency-Key
    header (same key) is the cross-instance dedupe for 24h."""

    def __init__(self) -> None:
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def seen(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            ts = self._seen.get(key)
            return ts is not None and now - ts < _IDEMPOTENCY_TTL_SECONDS

    def add(self, key: str) -> None:
        with self._lock:
            if len(self._seen) >= _IDEMPOTENCY_MAX:
                self._seen.clear()
            self._seen[key] = time.monotonic()

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()


idempotency_cache = _IdempotencyCache()


@router.get("/features", response_model=FeaturesResponse, tags=["system"])
async def features(settings: Annotated[Settings, Depends(get_settings_dep)]) -> FeaturesResponse:
    from app.knowledge.provider import get_knowledge_provider

    inf_enabled, inf_reason = inference_status(settings)
    em_enabled, em_reason = email_status(settings)
    try:
        knowledge_version = str(get_knowledge_provider().version)
    except Exception:  # read-only use of the knowledge layer; never fail the probe
        knowledge_version = "none"
    return FeaturesResponse(
        inference=FeatureFlag(enabled=inf_enabled, reason=inf_reason),
        email=FeatureFlag(enabled=em_enabled, reason=em_reason),
        image_storage=FeatureFlag(enabled=False, reason=IMAGE_STORAGE_REASON),
        research=FeatureFlag(
            enabled=False,
            reason=None if settings.sosu_research_enabled else "research_disabled",
        ),
        knowledge_version=knowledge_version,
        build=build_sha(),
    )


def _invalid(reason: str, details: list[Any] | None = None) -> SosuError:
    return SosuError(
        ErrorCode.INVALID_REQUEST,
        INVALID_TOKEN_MESSAGE,
        details=details or [{"reason": reason}],
    )


@router.post(
    "/report-email",
    response_model=SuccessEnvelope[ReportEmailResultV1],
    responses={
        422: {"model": ErrorEnvelope, "description": "INVALID_REQUEST"},
        413: {"model": ErrorEnvelope, "description": "IMAGE_TOO_LARGE (request body cap)"},
        429: {"model": ErrorEnvelope, "description": "RATE_LIMITED (per-instance backstop)"},
        502: {"model": ErrorEnvelope, "description": "EMAIL_DELIVERY_FAILED"},
        503: {"model": ErrorEnvelope, "description": "SERVICE_UNAVAILABLE (email disabled)"},
    },
    tags=["delivery"],
    summary="검증된 리포트를 이메일로 발송",
)
async def report_email(
    request: Request,
    body: ReportEmailRequestV1,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    provider: Annotated[EmailProvider, Depends(get_email_provider)],
) -> SuccessEnvelope[ReportEmailResultV1]:
    request_id = str(getattr(request.state, "request_id", "unknown"))

    enabled, reason = email_status(settings)
    if not enabled:
        raise SosuError(
            ErrorCode.SERVICE_UNAVAILABLE,
            EMAIL_DISABLED_MESSAGE,
            details=[{"reason": reason}],
            retryable=False,
        )

    email = body.email.strip()
    if not EMAIL_RE.fullmatch(email) or ".." in email:
        raise SosuError(
            ErrorCode.INVALID_REQUEST,
            "이메일 주소 형식이 올바르지 않습니다.",
            details=[{"loc": ["body", "email"], "msg": "invalid email", "type": "email"}],
        )

    model: type[DiagnosisReportV1] | type[PrescriptionReportV1] = (
        DiagnosisReportV1 if body.kind == "diagnosis" else PrescriptionReportV1
    )
    try:
        report = model.model_validate(body.report)
    except ValidationError as exc:
        raise _invalid("report_schema", pydantic_error_details(exc.errors())) from exc

    data = report.model_dump(mode="json")
    failure = verify_report(settings, body.delivery_token, body.kind, body.request_id, data)
    if failure is not None:
        logger.info("request_id=%s report_email rejected=%s", request_id, failure)
        raise _invalid(failure)

    key = hashlib.sha256(f"{body.delivery_token}|{email.lower()}".encode()).hexdigest()
    if idempotency_cache.seen(key):
        return SuccessEnvelope[ReportEmailResultV1](
            request_id=request_id, data=ReportEmailResultV1(status="duplicate")
        )

    subject, text, html = render_report_email(report)
    try:
        await provider.send(
            EmailMessage(to=email, subject=subject, text=text, html=html, idempotency_key=key)
        )
    except EmailDeliveryError as exc:
        logger.warning("request_id=%s report_email delivery_failed=%s", request_id, exc)
        raise SosuError(ErrorCode.EMAIL_DELIVERY_FAILED, DELIVERY_FAILED_MESSAGE) from exc

    idempotency_cache.add(key)
    logger.info("request_id=%s report_email sent kind=%s", request_id, body.kind)
    return SuccessEnvelope[ReportEmailResultV1](
        request_id=request_id, data=ReportEmailResultV1(status="sent")
    )
