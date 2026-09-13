"""Typed service errors. API layer maps these to the envelope; never leak provider text."""

from __future__ import annotations

from typing import Any

from app.contracts.envelope import ErrorCode

_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_REQUEST: 422,
    ErrorCode.INSUFFICIENT_INPUT: 422,
    ErrorCode.INVALID_IMAGE_TYPE: 415,
    ErrorCode.IMAGE_TOO_LARGE: 413,
    ErrorCode.INVALID_IMAGE_COUNT: 422,
    ErrorCode.INVALID_INSTAGRAM_URL: 422,
    ErrorCode.MODEL_TIMEOUT: 504,
    ErrorCode.MODEL_PROVIDER_ERROR: 502,
    ErrorCode.MODEL_SCHEMA_ERROR: 502,
    ErrorCode.MODEL_CONTENT_ERROR: 502,
    ErrorCode.REPAIR_FAILED: 502,
    ErrorCode.INTERNAL_ERROR: 500,
}

_RETRYABLE: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.MODEL_TIMEOUT,
        ErrorCode.MODEL_PROVIDER_ERROR,
        ErrorCode.MODEL_SCHEMA_ERROR,
        ErrorCode.MODEL_CONTENT_ERROR,
        ErrorCode.REPAIR_FAILED,
    }
)


class SosuError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: list[Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []
        self.retryable = retryable if retryable is not None else code in _RETRYABLE

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS[self.code]
