"""Public v1 endpoints. Contract of record: contracts/openapi.json + contracts/fixtures/*."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, ValidationError

from app.api.deps import get_diagnosis_service, get_prescription_service, get_settings_dep
from app.api.errors import pydantic_error_details
from app.config import Settings
from app.contracts.diagnosis import DiagnosisReportV1, SurveyDiagnosisRequestV1
from app.contracts.envelope import ErrorCode, ErrorEnvelope, HealthResponse, SuccessEnvelope
from app.contracts.prescription import PrescriptionReportV1, PrescriptionRequestV1
from app.domain.errors import SosuError
from app.domain.normalizer import normalize_survey
from app.domain.sufficiency import ensure_sufficient_input
from app.images import normalize as image_normalize
from app.images.types import (
    INSIGHT_IMAGE_COUNT,
    INSIGHT_IMAGE_MAX_BYTES,
    PRODUCT_IMAGE_MAX_BYTES,
    NormalizedImage,
)
from app.services.diagnosis_service import DiagnosisService
from app.services.prescription_service import PrescriptionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorEnvelope, "description": "IMAGE_TOO_LARGE"},
    415: {"model": ErrorEnvelope, "description": "INVALID_IMAGE_TYPE"},
    422: {
        "model": ErrorEnvelope,
        "description": (
            "INVALID_REQUEST | INSUFFICIENT_INPUT | INVALID_IMAGE_COUNT | INVALID_INSTAGRAM_URL"
        ),
    },
    500: {"model": ErrorEnvelope, "description": "INTERNAL_ERROR"},
    502: {
        "model": ErrorEnvelope,
        "description": (
            "MODEL_PROVIDER_ERROR | MODEL_SCHEMA_ERROR | MODEL_CONTENT_ERROR | REPAIR_FAILED"
        ),
    },
    504: {"model": ErrorEnvelope, "description": "MODEL_TIMEOUT"},
}

_PAYLOAD_DESC = "JSON string of {model}. Sent as a text form field, not a JSON body."


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _parse_payload[M: BaseModel](payload: str, model: type[M]) -> M:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SosuError(
            ErrorCode.INVALID_REQUEST,
            "payload 필드는 유효한 JSON 문자열이어야 합니다.",
            details=[{"loc": ["payload"], "msg": "invalid json", "type": "json_invalid"}],
        ) from exc
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        details = pydantic_error_details(exc.errors())
        if any("INVALID_INSTAGRAM_URL" in d["msg"] for d in details):
            raise SosuError(
                ErrorCode.INVALID_INSTAGRAM_URL,
                "Instagram Reel URL 형식이 아닙니다.",
                details=[{"loc": ["payload", "instagram_url"]}],
            ) from exc
        raise SosuError(
            ErrorCode.INVALID_REQUEST,
            "payload가 계약(SurveyDiagnosisRequestV1/PrescriptionRequestV1)과 일치하지 않습니다.",
            details=details,
        ) from exc


async def _read_capped(upload: UploadFile, *, max_bytes: int, label: str) -> bytes:
    """Read at most max_bytes+1 so an oversize upload never fully lands in memory."""
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise SosuError(
            ErrorCode.IMAGE_TOO_LARGE,
            f"{label} 이미지가 허용 용량을 초과했습니다.",
            details=[{"limit_bytes": max_bytes, "field": label}],
        )
    return data


def _is_absent(upload: UploadFile | None) -> bool:
    if upload is None:
        return True
    return not upload.filename and (upload.size in (0, None))


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(settings: Annotated[Settings, Depends(get_settings_dep)]) -> HealthResponse:
    return HealthResponse(gemini_configured=settings.gemini_configured)


@router.post(
    "/diagnosis",
    response_model=SuccessEnvelope[DiagnosisReportV1],
    responses=_ERROR_RESPONSES,
    tags=["diagnosis"],
    summary="문진표 → 릴스 진단서",
    openapi_extra={
        "x-multipart-fields": {
            "payload": "SurveyDiagnosisRequestV1 (JSON string)",
            "product_image": "optional file, 0..1, image/jpeg|png|webp, <= 1.25 MB",
        }
    },
)
async def diagnosis(
    request: Request,
    payload: Annotated[
        str, Form(description=_PAYLOAD_DESC.format(model="SurveyDiagnosisRequestV1"))
    ],
    service: Annotated[DiagnosisService, Depends(get_diagnosis_service)],
    product_image: Annotated[
        UploadFile | None,
        File(description="Optional product photo (0..1). image/jpeg, image/png, image/webp."),
    ] = None,
) -> SuccessEnvelope[DiagnosisReportV1]:
    request_id = _request_id(request)
    req = _parse_payload(payload, SurveyDiagnosisRequestV1)
    declared = normalize_survey(req.answers)

    has_image = not _is_absent(product_image)
    ensure_sufficient_input(declared, has_image=has_image)

    normalized: NormalizedImage | None = None
    if has_image and product_image is not None:
        image_normalize.validate_upload(
            product_image.content_type,
            product_image.size or 0,
            max_bytes=PRODUCT_IMAGE_MAX_BYTES,
        )
        raw = await _read_capped(
            product_image, max_bytes=PRODUCT_IMAGE_MAX_BYTES, label="product_image"
        )
        normalized = image_normalize.normalize_product_image(raw)

    report = await service.run(req, normalized, request_id=request_id)
    return SuccessEnvelope[DiagnosisReportV1](request_id=request_id, data=report)


@router.post(
    "/prescription",
    response_model=SuccessEnvelope[PrescriptionReportV1],
    responses=_ERROR_RESPONSES,
    tags=["prescription"],
    summary="릴스 URL + Insight 스크린샷 3장 → 릴스 처방전",
    openapi_extra={
        "x-multipart-fields": {
            "payload": "PrescriptionRequestV1 (JSON string)",
            "insight_images": (
                "exactly 3 files, image/jpeg|png|webp, each <= 900 KB, combined <= 2.7 MB"
            ),
        }
    },
)
async def prescription(
    request: Request,
    payload: Annotated[str, Form(description=_PAYLOAD_DESC.format(model="PrescriptionRequestV1"))],
    insight_images: Annotated[
        list[UploadFile],
        File(description="Exactly 3 Instagram Insight screenshots (jpeg/png/webp)."),
    ],
    service: Annotated[PrescriptionService, Depends(get_prescription_service)],
) -> SuccessEnvelope[PrescriptionReportV1]:
    request_id = _request_id(request)
    req = _parse_payload(payload, PrescriptionRequestV1)

    files = [f for f in insight_images if not _is_absent(f)]
    if len(files) != INSIGHT_IMAGE_COUNT:
        raise SosuError(
            ErrorCode.INVALID_IMAGE_COUNT,
            f"Insight 스크린샷은 정확히 {INSIGHT_IMAGE_COUNT}장이어야 합니다.",
            details=[{"expected": INSIGHT_IMAGE_COUNT, "actual": len(files)}],
        )

    for f in files:
        image_normalize.validate_upload(
            f.content_type, f.size or 0, max_bytes=INSIGHT_IMAGE_MAX_BYTES
        )

    raws: list[bytes] = []
    for idx, f in enumerate(files):
        raws.append(
            await _read_capped(f, max_bytes=INSIGHT_IMAGE_MAX_BYTES, label=f"insight_images[{idx}]")
        )
    image_normalize.validate_insight_batch([len(r) for r in raws])

    normalized = [image_normalize.normalize_insight_screenshot(r) for r in raws]
    report = await service.run(req, normalized, request_id=request_id)
    return SuccessEnvelope[PrescriptionReportV1](request_id=request_id, data=report)
