"""Phase 2 security: fail-closed inference gate, body cap, per-instance limiter, tokens."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from app.api.deps import get_diagnosis_service, get_prescription_service
from app.config import get_settings
from app.contracts.diagnosis import DiagnosisReportV1
from app.main import create_app
from app.security.ratelimit import TokenBucketLimiter
from app.security.runtime import PUBLIC_RUNTIME_ENV_MARKERS
from app.security.tokens import sign_report, verify_report
from fastapi.testclient import TestClient

from tests.api_samples import diagnosis_report_dict, diagnosis_request_dict


class _ExplodingService:
    calls = 0

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        _ExplodingService.calls += 1
        raise AssertionError("service must not be reached when the gate is closed")


class _OkDiagnosis:
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        return DiagnosisReportV1.model_validate(diagnosis_report_dict())


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    for name in (
        *PUBLIC_RUNTIME_ENV_MARKERS,
        "SOSU_ENV",
        "SOSU_PUBLIC_INFERENCE_ENABLED",
        "VERCEL_GIT_COMMIT_SHA",
        "SOSU_DELIVERY_SIGNING_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def _client(service: Any) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_diagnosis_service] = lambda: service
    app.dependency_overrides[get_prescription_service] = lambda: service
    return TestClient(app)


def _diag(client: TestClient, **kw: Any) -> Any:
    return client.post(
        "/api/v1/diagnosis", data={"payload": json.dumps(diagnosis_request_dict())}, **kw
    )


@pytest.mark.parametrize(
    "flag",
    [
        ("VERCEL", "1"),
        ("SOSU_ENV", "production"),
        ("VERCEL_ENV", "production"),
        ("AWS_LAMBDA_FUNCTION_NAME", "sosu-py-fn"),
    ],
)
@pytest.mark.parametrize("path", ["/api/v1/diagnosis", "/api/v1/prescription"])
def test_public_runtime_fails_closed_before_parsing(
    env: pytest.MonkeyPatch, flag: tuple[str, str], path: str
) -> None:
    env.setenv(*flag)
    get_settings.cache_clear()
    _ExplodingService.calls = 0
    client = _client(_ExplodingService())
    # Deliberately invalid body: the gate must answer before any parsing happens.
    resp = client.post(path, content=b"not-multipart", headers={"content-type": "text/plain"})
    assert resp.status_code == 503
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert body["error"]["retryable"] is False
    assert "중단" in body["error"]["message"]
    assert _ExplodingService.calls == 0
    assert resp.headers["x-request-id"] == body["request_id"]


def test_public_runtime_opens_only_with_explicit_flag(env: pytest.MonkeyPatch) -> None:
    env.setenv("VERCEL", "1")
    env.setenv("SOSU_PUBLIC_INFERENCE_ENABLED", "true")
    get_settings.cache_clear()
    resp = _diag(_client(_OkDiagnosis()))
    assert resp.status_code == 200, resp.text


def test_local_behaviour_unchanged(env: pytest.MonkeyPatch) -> None:
    resp = _diag(_client(_OkDiagnosis()))
    assert resp.status_code == 200
    assert resp.json()["delivery_token"] is None  # no signing secret configured


def test_cors_headers_on_gate_rejection(env: pytest.MonkeyPatch) -> None:
    env.setenv("VERCEL", "1")
    env.setenv("SOSU_CORS_ORIGINS", "http://localhost:5173,https://sosu-rosy.vercel.app")
    get_settings.cache_clear()
    resp = _client(_ExplodingService()).post(
        "/api/v1/diagnosis",
        data={"payload": "{}"},
        headers={"Origin": "https://sosu-rosy.vercel.app"},
    )
    assert resp.status_code == 503
    assert resp.headers.get("access-control-allow-origin") == "https://sosu-rosy.vercel.app"


def test_body_cap_content_length(env: pytest.MonkeyPatch) -> None:
    client = _client(_ExplodingService())
    resp = client.post(
        "/api/v1/diagnosis",
        content=b"x" * 4_000_001,
        headers={"content-type": "application/octet-stream"},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_body_cap_streamed_without_content_length(env: pytest.MonkeyPatch) -> None:
    client = _client(_ExplodingService())

    def chunks() -> Iterator[bytes]:
        for _ in range(5):
            yield b"y" * 1_000_000

    resp = client.post(
        "/api/v1/report-email",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_per_instance_rate_limit_on_public_runtime(env: pytest.MonkeyPatch) -> None:
    env.setenv("VERCEL", "1")
    env.setenv("SOSU_PUBLIC_INFERENCE_ENABLED", "true")
    env.setenv("SOSU_RATELIMIT_AI_PER_MINUTE", "2")
    get_settings.cache_clear()
    client = _client(_OkDiagnosis())
    codes = [_diag(client).status_code for _ in range(3)]
    assert codes[:2] == [200, 200]
    assert codes[2] == 429
    assert _diag(client).json()["error"]["code"] == "RATE_LIMITED"


def test_build_header_and_no_header_when_unknown(env: pytest.MonkeyPatch) -> None:
    client = _client(_OkDiagnosis())
    assert "x-sosu-build" not in client.get("/api/v1/health").headers
    env.setenv("VERCEL_GIT_COMMIT_SHA", "0123456789abcdef0123")
    resp = client.get("/api/v1/health")
    assert resp.headers["x-sosu-build"] == "0123456789ab"


def test_token_bucket_refills() -> None:
    lim = TokenBucketLimiter(per_minute=60, burst=1)
    assert lim.allow("a", now=0.0)
    assert not lim.allow("a", now=0.1)
    assert lim.allow("a", now=1.2)
    assert lim.allow("b", now=0.1)


def test_token_sign_verify_tamper_expiry(env: pytest.MonkeyPatch) -> None:
    env.setenv("SOSU_DELIVERY_SIGNING_SECRET", "s" * 32)
    get_settings.cache_clear()
    s = get_settings()
    data = DiagnosisReportV1.model_validate(diagnosis_report_dict()).model_dump(mode="json")
    tok = sign_report(s, "diagnosis", "rid-1", data, now=1_000_000)
    assert tok is not None and tok.startswith("1000000.")
    assert verify_report(s, tok, "diagnosis", "rid-1", data, now=1_000_100) is None
    tampered = json.loads(json.dumps(data))
    tampered["brand"]["name"] = "다른 브랜드"
    assert verify_report(s, tok, "diagnosis", "rid-1", tampered, now=1_000_100) == (
        "signature_mismatch"
    )
    assert verify_report(s, tok, "prescription", "rid-1", data, now=1_000_100) is not None
    assert verify_report(s, tok, "diagnosis", "rid-2", data, now=1_000_100) is not None
    assert verify_report(s, tok, "diagnosis", "rid-1", data, now=1_000_000 + 86_401) == (
        "token_expired"
    )
    assert verify_report(s, "garbage", "diagnosis", "rid-1", data) == "malformed_token"


def test_default_cors_includes_production_web() -> None:
    from app.config import Settings

    assert "https://sosu-rosy.vercel.app" in Settings.model_fields["sosu_cors_origins"].default


def test_secrets_never_in_settings_repr(env: pytest.MonkeyPatch) -> None:
    env.setenv("SOSU_DELIVERY_SIGNING_SECRET", "topsecretvalue123")
    env.setenv("RESEND_API_KEY", "re_supersecret")
    get_settings.cache_clear()
    text = repr(get_settings())
    assert "topsecretvalue123" not in text
    assert "re_supersecret" not in text
