"""Phase 2 routes: GET /api/v1/features and POST /api/v1/report-email."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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
from app.security.runtime import build_sha, email_status, guidebook_status, inference_status
from app.security.tokens import sign_guidebook_link, verify_guidebook_link, verify_report

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
    gb_enabled, gb_reason = guidebook_status(settings)
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
        guidebook=FeatureFlag(enabled=gb_enabled, reason=gb_reason),
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

    guidebook_link = _guidebook_link(settings)
    subject, text, html = render_report_email(
        report,
        guidebook_link=guidebook_link,
        guidebook_link_days=max(1, settings.sosu_guidebook_link_max_age_seconds // 86_400),
    )
    try:
        await provider.send(
            EmailMessage(to=email, subject=subject, text=text, html=html, idempotency_key=key)
        )
    except EmailDeliveryError as exc:
        logger.warning("request_id=%s report_email delivery_failed=%s", request_id, exc)
        raise SosuError(ErrorCode.EMAIL_DELIVERY_FAILED, DELIVERY_FAILED_MESSAGE) from exc

    idempotency_cache.add(key)
    logger.info(
        "request_id=%s report_email sent kind=%s guidebook=%s",
        request_id,
        body.kind,
        guidebook_link is not None,
    )
    return SuccessEnvelope[ReportEmailResultV1](
        request_id=request_id, data=ReportEmailResultV1(status="sent")
    )


# ------------------------------------------------------------------ guidebook e-book

_NO_STORE = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}
_GUIDEBOOK_GONE_HTML = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SOSU 가이드북</title>
<body style="font-family:sans-serif;background:#1b1f20;color:#f4f2ec;display:grid;
place-items:center;min-height:100vh;margin:0;text-align:center;padding:24px">
<div><h1 style="font-size:20px">{title}</h1><p style="opacity:.8">{body}</p></div></body></html>"""


def _guidebook_link(settings: Settings) -> str | None:
    if not guidebook_status(settings)[0]:
        return None
    token = sign_guidebook_link(settings)
    if token is None:
        return None
    base = settings.sosu_public_api_base_url.rstrip("/")
    return f"{base}/api/v1/guidebook?t={token}"


def _guidebook_page(status: int, title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        _GUIDEBOOK_GONE_HTML.format(title=title, body=body), status_code=status, headers=_NO_STORE
    )


@router.get("/guidebook", tags=["delivery"], summary="이메일의 서명된 링크 → 가이드북 PDF로 이동")
async def guidebook(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    t: Annotated[str, Query(max_length=128)] = "",
) -> Response:
    """302 to the e-book only for a valid, unexpired link from a report e-mail.
    The storage URL itself is never shown in pages, logs or the API contract."""
    enabled, _ = guidebook_status(settings)
    if not enabled:
        return _guidebook_page(404, "가이드북을 준비 중이에요", "잠시 후 다시 시도해 주세요.")
    failure = verify_guidebook_link(settings, t)
    if failure is not None:
        logger.info("guidebook link rejected=%s", failure)
        return _guidebook_page(
            410,
            "링크가 만료되었어요",
            "진단서나 처방전을 다시 받으면 새 가이드북 링크가 함께 발송돼요.",
        )
    return RedirectResponse(
        settings.sosu_guidebook_url.get_secret_value().strip(), status_code=302, headers=_NO_STORE
    )
