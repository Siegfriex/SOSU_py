"""Response envelope, stable error codes, health payload."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


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
