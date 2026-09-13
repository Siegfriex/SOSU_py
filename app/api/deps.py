"""FastAPI dependencies. Everything here is overridable through `app.dependency_overrides`."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.gemini.gateway import GeminiGateway
from app.services.diagnosis_service import DiagnosisService
from app.services.prescription_service import PrescriptionService


def get_settings_dep() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def _build_gateway() -> GeminiGateway:
    # Imported lazily so the API module loads even if the vendor SDK is unavailable at import
    # time; a missing/placeholder key surfaces as MODEL_PROVIDER_ERROR at call time, not here.
    from app.gemini.client import GoogleGenAIGateway

    return GoogleGenAIGateway(get_settings())


def get_gateway() -> GeminiGateway:
    return _build_gateway()


def get_diagnosis_service(
    gateway: Annotated[GeminiGateway, Depends(get_gateway)],
) -> DiagnosisService:
    return DiagnosisService(gateway)


def get_prescription_service(
    gateway: Annotated[GeminiGateway, Depends(get_gateway)],
) -> PrescriptionService:
    return PrescriptionService(gateway)
