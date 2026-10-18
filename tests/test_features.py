"""GET /api/v1/features — public posture probe (not enveloped)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.config import get_settings
from app.main import create_app
from app.security.runtime import PUBLIC_RUNTIME_ENV_MARKERS
from fastapi.testclient import TestClient


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    for name in (
        *PUBLIC_RUNTIME_ENV_MARKERS,
        "SOSU_ENV",
        "SOSU_PUBLIC_INFERENCE_ENABLED",
        "SOSU_PUBLIC_EMAIL_ENABLED",
        "VERCEL_GIT_COMMIT_SHA",
    ):
        monkeypatch.delenv(name, raising=False)
    for name in ("RESEND_API_KEY", "SOSU_EMAIL_FROM", "SOSU_DELIVERY_SIGNING_SECRET"):
        monkeypatch.setenv(name, "")
    # Pin the flags: a developer .env/.env.local (e.g. one opening inference) must not leak in.
    monkeypatch.setenv("SOSU_ENV", "development")
    monkeypatch.setenv("SOSU_PUBLIC_INFERENCE_ENABLED", "false")
    monkeypatch.setenv("SOSU_PUBLIC_EMAIL_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def _get() -> dict:
    resp = TestClient(create_app()).get("/api/v1/features")
    assert resp.status_code == 200
    return resp.json()


def test_shape_local(env: pytest.MonkeyPatch) -> None:
    body = _get()
    assert set(body) == {
        "contract_version",
        "inference",
        "email",
        "image_storage",
        "research",
        "knowledge_version",
        "build",
    }
    assert body["contract_version"] == "1.0"
    assert body["inference"] == {"enabled": True, "reason": None}
    assert body["email"]["enabled"] is False
    assert body["email"]["reason"] == "resend_not_configured"
    assert body["image_storage"]["enabled"] is False
    assert body["image_storage"]["reason"]
    assert body["research"]["enabled"] is False
    assert isinstance(body["knowledge_version"], str) and body["knowledge_version"]
    assert body["build"] is None
    assert "ok" not in body  # not enveloped


def test_production_reports_closed(env: pytest.MonkeyPatch) -> None:
    env.setenv("VERCEL", "1")
    env.setenv("VERCEL_GIT_COMMIT_SHA", "abcdef1234567890")
    get_settings.cache_clear()
    body = _get()
    assert body["inference"] == {"enabled": False, "reason": "public_inference_disabled"}
    assert body["build"] == "abcdef123456"
    env.setenv("SOSU_PUBLIC_INFERENCE_ENABLED", "true")
    get_settings.cache_clear()
    assert _get()["inference"]["enabled"] is True


def test_email_enabled_only_with_all_settings(env: pytest.MonkeyPatch) -> None:
    env.setenv("RESEND_API_KEY", "re_x")
    env.setenv("SOSU_EMAIL_FROM", "SOSU <r@example.com>")
    get_settings.cache_clear()
    assert _get()["email"] == {"enabled": False, "reason": "signing_secret_not_configured"}
    env.setenv("SOSU_DELIVERY_SIGNING_SECRET", "z" * 32)
    get_settings.cache_clear()
    assert _get()["email"] == {"enabled": True, "reason": None}
    env.setenv("SOSU_ENV", "production")
    get_settings.cache_clear()
    assert _get()["email"] == {"enabled": False, "reason": "public_email_disabled"}
