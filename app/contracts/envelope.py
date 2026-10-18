"""Response envelope, stable error codes, health payload."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"
    INVALID_IMAGE_TYPE = "INVALID_IMAGE_TYPE"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    INVALID_IMAGE_COUNT = "INVALID_IMAGE_COUNT"
    INVALID_INSTAGRAM_URL = "INVALID_INSTAGRAM_URL"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
    MODEL_SCHEMA_ERROR = "MODEL_SCHEMA_ERROR"
    MODEL_CONTENT_ERROR = "MODEL_CONTENT_ERROR"
    REPAIR_FAILED = "REPAIR_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # Phase 2 (additive)
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    EMAIL_DELIVERY_FAILED = "EMAIL_DELIVERY_FAILED"


class ApiError(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool
    details: list[Any] = Field(default_factory=list)


class SuccessEnvelope[T](BaseModel):
    ok: Literal[True] = True
    request_id: str
    contract_version: Literal["1.0"] = "1.0"
    data: T
    delivery_token: str | None = Field(
        default=None,
        description=(
            "Opaque server-signed token '<issued_at_unix>.<hmac hex>' over this report. "
            "Echo it to POST /api/v1/report-email. null when report delivery is not configured."
        ),
    )


class ErrorEnvelope(BaseModel):
    ok: Literal[False] = False
    request_id: str
    contract_version: Literal["1.0"] = "1.0"
    error: ApiError


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["sosu-ai"] = "sosu-ai"
    contract_version: Literal["1.0"] = "1.0"
    gemini_configured: bool


class FeatureFlag(BaseModel):
    enabled: bool
    reason: str | None = None


class FeaturesResponse(BaseModel):
    """GET /api/v1/features — plain JSON (not enveloped), like /health."""

    contract_version: Literal["1.0"] = "1.0"
    inference: FeatureFlag
    email: FeatureFlag
    image_storage: FeatureFlag
    research: FeatureFlag
    guidebook: FeatureFlag = FeatureFlag(enabled=False, reason="guidebook_url_not_configured")
    knowledge_version: str
    build: str | None = None


class ReportEmailRequestV1(BaseModel):
    """POST /api/v1/report-email JSON body. `report` is the success envelope's `data`, echoed."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["diagnosis", "prescription"]
    report: dict[str, Any]
    request_id: str = Field(min_length=1, max_length=64)
    delivery_token: str = Field(min_length=3, max_length=200)
    email: str = Field(min_length=3, max_length=254)


class ReportEmailResultV1(BaseModel):
    status: Literal["sent", "duplicate"]
