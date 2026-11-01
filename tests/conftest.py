from __future__ import annotations

from typing import Any

import pytest

from tests import helpers

# Settings read SOSU_py/.env.local; a developer's real e-mail credentials there must not leak into
# tests (CI has no .env.local). Empty env vars win over the dotenv file; tests that need a value
# set it themselves.
_ISOLATED_ENV = (
    "SOSU_SMTP_USERNAME",
    "SOSU_SMTP_PASSWORD",
    "RESEND_API_KEY",
    "SOSU_EMAIL_FROM",
    "SOSU_DELIVERY_SIGNING_SECRET",
    "SOSU_GUIDEBOOK_URL",
)


@pytest.fixture(autouse=True)
def _isolate_email_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    for name in _ISOLATED_ENV:
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()


@pytest.fixture
def sample_answers() -> dict[str, Any]:
    return helpers.sample_answers_dict()


@pytest.fixture
def sample_diagnosis_request() -> dict[str, Any]:
    return helpers.sample_diagnosis_request_dict()


@pytest.fixture
def sample_diagnosis_report_dict() -> dict[str, Any]:
    return helpers.sample_diagnosis_report_dict()


@pytest.fixture
def sample_prescription_request() -> dict[str, Any]:
    return helpers.sample_prescription_request_dict()


@pytest.fixture
def sample_prescription_report_dict() -> dict[str, Any]:
    return helpers.sample_prescription_report_dict()
