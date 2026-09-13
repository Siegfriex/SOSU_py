"""FastAPI application factory."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic.json_schema import models_json_schema
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import envelope_dict, internal_error, pydantic_error_details
from app.api.v1 import router as v1_router
from app.config import CONTRACT_VERSION, get_settings
from app.contracts.diagnosis import SurveyDiagnosisRequestV1
from app.contracts.envelope import ErrorCode
from app.contracts.prescription import PrescriptionRequestV1
from app.domain.errors import SosuError
from app.logging_setup import configure_logging

logger = logging.getLogger("sosu.api")

_SAFE_REQUEST_ID = re.compile(r"[^A-Za-z0-9._-]")
_REQUEST_ID_MAX = 64

OPENAPI_TAGS = [
    {"name": "system", "description": "Health / readiness."},
    {"name": "diagnosis", "description": "Workflow A — 문진표 → DiagnosisReportV1."},
    {
        "name": "prescription",
        "description": "Workflow B — Insight 스크린샷 → PrescriptionReportV1.",
    },
]


def _sanitize_request_id(raw: str | None) -> str:
    if raw:
        cleaned = _SAFE_REQUEST_ID.sub("", raw)[:_REQUEST_ID_MAX]
        if cleaned:
            return cleaned
    return uuid.uuid4().hex


def _rid(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return str(rid) if rid else _sanitize_request_id(request.headers.get("x-request-id"))


# Models carried inside the multipart `payload` text field. FastAPI cannot see through the JSON
# string, so they are registered in components.schemas explicitly for the frontend contract.
PAYLOAD_MODELS = (SurveyDiagnosisRequestV1, PrescriptionRequestV1)


def _openapi_with_payload_models(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    _, defs = models_json_schema(
        [(m, "validation") for m in PAYLOAD_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in defs.get("$defs", {}).items():
        components.setdefault(name, definition)
    schema["x-payload-models"] = {
        "/api/v1/diagnosis": "#/components/schemas/SurveyDiagnosisRequestV1",
        "/api/v1/prescription": "#/components/schemas/PrescriptionRequestV1",
    }
    app.openapi_schema = schema
    return schema


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.sosu_log_level)

    app = FastAPI(
        title="SOSU AI Service",
        version=CONTRACT_VERSION,
        description=(
            "Instagram Reels 진단/처방 AI 서비스. "
            "Public contract of record: contracts/openapi.json + contracts/fixtures/*."
        ),
        openapi_tags=OPENAPI_TAGS,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = _sanitize_request_id(request.headers.get("x-request-id"))
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(SosuError)
    async def sosu_error_handler(request: Request, exc: SosuError) -> JSONResponse:
        rid = _rid(request)
        logger.info("request_id=%s error_code=%s", rid, exc.code)
        return JSONResponse(status_code=exc.http_status, content=envelope_dict(exc, rid))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = _rid(request)
        err = SosuError(
            ErrorCode.INVALID_REQUEST,
            "요청 형식이 계약과 일치하지 않습니다.",
            details=pydantic_error_details(list(exc.errors())),
        )
        return JSONResponse(status_code=422, content=envelope_dict(err, rid))

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        rid = _rid(request)
        if exc.status_code >= 500:
            return JSONResponse(
                status_code=exc.status_code, content=internal_error(rid).model_dump(mode="json")
            )
        err = SosuError(
            ErrorCode.INVALID_REQUEST,
            str(exc.detail) if isinstance(exc.detail, str) else "잘못된 요청입니다.",
            details=[{"http_status": exc.status_code}],
        )
        return JSONResponse(status_code=exc.status_code, content=envelope_dict(err, rid))

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = _rid(request)
        logger.exception("request_id=%s unhandled error", rid)
        return JSONResponse(status_code=500, content=internal_error(rid).model_dump(mode="json"))

    app.include_router(v1_router)
    app.openapi = lambda: _openapi_with_payload_models(app)  # type: ignore[method-assign]
    return app


app = create_app()
