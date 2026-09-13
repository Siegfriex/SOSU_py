"""Shared error → envelope serializer used by the app handlers and fixture scripts."""

from __future__ import annotations

from typing import Any

from app.contracts.envelope import ApiError, ErrorCode, ErrorEnvelope
from app.domain.errors import SosuError

GENERIC_INTERNAL_MESSAGE = "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


def envelope_for(error: SosuError, request_id: str) -> ErrorEnvelope:
    return ErrorEnvelope(
        request_id=request_id,
        error=ApiError(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            details=list(error.details),
        ),
    )


def envelope_dict(error: SosuError, request_id: str) -> dict[str, Any]:
    return envelope_for(error, request_id).model_dump(mode="json")


def pydantic_error_details(errors: list[Any]) -> list[dict[str, Any]]:
    """Keep only loc/msg/type — never echo raw input values back to the client."""
    out: list[dict[str, Any]] = []
    for err in errors:
        out.append(
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
        )
    return out


def internal_error(request_id: str) -> ErrorEnvelope:
    return envelope_for(
        SosuError(ErrorCode.INTERNAL_ERROR, GENERIC_INTERNAL_MESSAGE, retryable=False),
        request_id,
    )
