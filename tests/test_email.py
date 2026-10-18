"""Report e-mail: signed-report verification, idempotency, fail-closed. No real e-mail is sent."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from app.api.delivery import idempotency_cache
from app.api.deps import get_diagnosis_service, get_prescription_service
from app.config import get_settings
from app.contracts.diagnosis import DiagnosisReportV1
from app.contracts.prescription import PrescriptionReportV1
from app.email.provider import (
    EmailDeliveryError,
    EmailMessage,
    NullProvider,
    ResendProvider,
    build_provider,
    get_email_provider,
)
from app.email.render import render_report_email
from app.main import create_app
from app.security.runtime import PUBLIC_RUNTIME_ENV_MARKERS
from app.security.tokens import sign_report
from fastapi.testclient import TestClient

from tests.api_samples import (
    diagnosis_report_dict,
    diagnosis_request_dict,
    prescription_report_dict,
)


class FakeProvider:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = fail

    async def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise EmailDeliveryError("boom")
        self.sent.append(message)


class _OkDiagnosis:
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        return DiagnosisReportV1.model_validate(diagnosis_report_dict())


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    for name in (*PUBLIC_RUNTIME_ENV_MARKERS, "SOSU_ENV", "SOSU_PUBLIC_EMAIL_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "re_test_not_real")
    monkeypatch.setenv("SOSU_EMAIL_FROM", "SOSU <report@example.com>")
    monkeypatch.setenv("SOSU_DELIVERY_SIGNING_SECRET", "k" * 32)
    get_settings.cache_clear()
    idempotency_cache.clear()
    yield monkeypatch
    get_settings.cache_clear()
    idempotency_cache.clear()


def _client(provider: Any) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_email_provider] = lambda: provider
    app.dependency_overrides[get_diagnosis_service] = lambda: _OkDiagnosis()
    app.dependency_overrides[get_prescription_service] = lambda: _OkDiagnosis()
    return TestClient(app)


def _body(kind: str = "diagnosis", **over: Any) -> dict[str, Any]:
    report = diagnosis_report_dict() if kind == "diagnosis" else prescription_report_dict()
    model = DiagnosisReportV1 if kind == "diagnosis" else PrescriptionReportV1
    data = model.model_validate(report).model_dump(mode="json")
    token = sign_report(get_settings(), kind, "rid-abc", data)
    body = {
        "kind": kind,
        "report": data,
        "request_id": "rid-abc",
        "delivery_token": token,
        "email": "owner@example.com",
    }
    body.update(over)
    return body


@pytest.mark.parametrize("kind", ["diagnosis", "prescription"])
def test_valid_token_sends_once_then_duplicate(env: pytest.MonkeyPatch, kind: str) -> None:
    fake = FakeProvider()
    client = _client(fake)
    body = _body(kind)
    r1 = client.post("/api/v1/report-email", json=body)
    assert r1.status_code == 200, r1.text
    assert r1.json()["ok"] is True
    assert r1.json()["data"] == {"status": "sent"}
    r2 = client.post("/api/v1/report-email", json=body)
    assert r2.json()["data"] == {"status": "duplicate"}
    assert len(fake.sent) == 1
    msg = fake.sent[0]
    assert msg.to == "owner@example.com"
    assert msg.subject.startswith("[SOSU]")
    assert len(msg.idempotency_key) == 64


def test_end_to_end_token_from_diagnosis_envelope(env: pytest.MonkeyPatch) -> None:
    fake = FakeProvider()
    client = _client(fake)
    env_resp = client.post(
        "/api/v1/diagnosis", data={"payload": json.dumps(diagnosis_request_dict())}
    ).json()
    token = env_resp["delivery_token"]
    assert token and "." in token
    # Echo exactly as a JS client would (re-serialized JSON).
    resp = client.post(
        "/api/v1/report-email",
        json={
            "kind": "diagnosis",
            "report": json.loads(json.dumps(env_resp["data"])),
            "request_id": env_resp["request_id"],
            "delivery_token": token,
            "email": "a.b+c@example.co.kr",
        },
    )
    assert resp.status_code == 200, resp.text
    assert len(fake.sent) == 1


def test_tampered_report_rejected(env: pytest.MonkeyPatch) -> None:
    fake = FakeProvider()
    body = _body()
    body["report"]["brand"]["name"] = "피싱 링크 http://evil.example"
    resp = _client(fake).post("/api/v1/report-email", json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"
    assert fake.sent == []


def test_wrong_request_id_rejected(env: pytest.MonkeyPatch) -> None:
    resp = _client(FakeProvider()).post("/api/v1/report-email", json=_body(request_id="other"))
    assert resp.status_code == 422


def test_expired_token_rejected(env: pytest.MonkeyPatch) -> None:
    body = _body()
    data = body["report"]
    body["delivery_token"] = sign_report(get_settings(), "diagnosis", "rid-abc", data, now=1000)
    resp = _client(FakeProvider()).post("/api/v1/report-email", json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"] == [{"reason": "token_expired"}]


@pytest.mark.parametrize(
    "email", ["not-an-email", "a@b", "x@example.com\r\nBcc: v@evil.com", "a..b@example.com"]
)
def test_bad_email_rejected(env: pytest.MonkeyPatch, email: str) -> None:
    fake = FakeProvider()
    resp = _client(fake).post("/api/v1/report-email", json=_body(email=email))
    assert resp.status_code == 422
    assert fake.sent == []


def test_extra_free_text_field_rejected(env: pytest.MonkeyPatch) -> None:
    resp = _client(FakeProvider()).post(
        "/api/v1/report-email", json=_body(html="<a href=evil>click</a>")
    )
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "drop", ["RESEND_API_KEY", "SOSU_EMAIL_FROM", "SOSU_DELIVERY_SIGNING_SECRET"]
)
def test_disabled_when_not_configured(env: pytest.MonkeyPatch, drop: str) -> None:
    body = _body()
    env.setenv(drop, "")
    get_settings.cache_clear()
    fake = FakeProvider()
    resp = _client(fake).post("/api/v1/report-email", json=body)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert fake.sent == []


def test_disabled_on_public_runtime_without_explicit_flag(env: pytest.MonkeyPatch) -> None:
    body = _body()
    env.setenv("VERCEL", "1")
    get_settings.cache_clear()
    fake = FakeProvider()
    resp = _client(fake).post("/api/v1/report-email", json=body)
    assert resp.status_code == 503
    env.setenv("SOSU_PUBLIC_EMAIL_ENABLED", "true")
    get_settings.cache_clear()
    resp = _client(fake).post("/api/v1/report-email", json=body)
    assert resp.status_code == 200
    assert len(fake.sent) == 1


def test_provider_failure_maps_to_email_delivery_failed(env: pytest.MonkeyPatch) -> None:
    body = _body()
    resp = _client(FakeProvider(fail=True)).post("/api/v1/report-email", json=body)
    assert resp.status_code == 502
    err = resp.json()["error"]
    assert err["code"] == "EMAIL_DELIVERY_FAILED"
    assert err["retryable"] is True
    assert "boom" not in resp.text
    # Failure is not cached → a retry can still send.
    ok = FakeProvider()
    assert _client(ok).post("/api/v1/report-email", json=body).json()["data"]["status"] == "sent"


def test_build_provider_selection(env: pytest.MonkeyPatch) -> None:
    assert isinstance(build_provider(get_settings()), ResendProvider)
    env.setenv("RESEND_API_KEY", "")
    get_settings.cache_clear()
    assert isinstance(build_provider(get_settings()), NullProvider)


def test_render_escapes_html() -> None:
    data = diagnosis_report_dict()
    data["brand"]["name"] = "<script>x</script>"
    subject, text, html = render_report_email(DiagnosisReportV1.model_validate(data))
    assert "진단서" in subject
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<script>x</script>" in text
