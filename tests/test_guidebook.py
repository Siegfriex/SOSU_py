"""Guidebook e-book: signed expiring link in report e-mails → /api/v1/guidebook → 302 to storage.
The storage URL is a secret: never in the e-mail, the features probe or an error page."""

from __future__ import annotations

import time
from collections.abc import Iterator
from html import escape

import pytest
from app.api.delivery import idempotency_cache
from app.config import get_settings
from app.contracts.diagnosis import DiagnosisReportV1
from app.contracts.prescription import PrescriptionReportV1
from app.email.render import render_report_email
from app.security.runtime import PUBLIC_RUNTIME_ENV_MARKERS
from app.security.tokens import sign_guidebook_link, verify_guidebook_link

from tests.api_samples import diagnosis_report_dict, prescription_report_dict
from tests.test_email import FakeProvider, _body, _client

STORAGE_URL = "https://example-blob.invalid/guidebook-Xy12.pdf"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    for name in (*PUBLIC_RUNTIME_ENV_MARKERS, "SOSU_ENV", "SOSU_PUBLIC_EMAIL_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "re_test_not_real")
    monkeypatch.setenv("SOSU_EMAIL_FROM", "SOSU <report@example.com>")
    monkeypatch.setenv("SOSU_DELIVERY_SIGNING_SECRET", "k" * 32)
    monkeypatch.setenv("SOSU_GUIDEBOOK_URL", STORAGE_URL)
    monkeypatch.setenv("SOSU_PUBLIC_API_BASE_URL", "https://api.example.test")
    get_settings.cache_clear()
    idempotency_cache.clear()
    yield monkeypatch
    get_settings.cache_clear()
    idempotency_cache.clear()


def test_token_roundtrip_expiry_and_tamper(env: pytest.MonkeyPatch) -> None:
    s = get_settings()
    now = int(time.time())
    token = sign_guidebook_link(s, now=now)
    assert token is not None
    assert verify_guidebook_link(s, token, now=now) is None
    assert verify_guidebook_link(s, token, now=now + 7 * 86_400 + 1) == "token_expired"
    exp, _, mac = token.partition(".")
    assert verify_guidebook_link(s, f"{int(exp) + 999}.{mac}", now=now) == "signature_mismatch"
    assert verify_guidebook_link(s, "nope", now=now) == "malformed_token"


def test_valid_link_redirects_without_caching(env: pytest.MonkeyPatch) -> None:
    token = sign_guidebook_link(get_settings())
    r = _client(FakeProvider()).get(f"/api/v1/guidebook?t={token}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == STORAGE_URL
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize("t", ["", "123.abc", f"{int(time.time()) - 10}.{'0' * 64}"])
def test_invalid_or_expired_link_is_410_page_without_url(env: pytest.MonkeyPatch, t: str) -> None:
    r = _client(FakeProvider()).get(f"/api/v1/guidebook?t={t}", follow_redirects=False)
    assert r.status_code == 410
    assert "링크가 만료되었어요" in r.text
    assert STORAGE_URL not in r.text


def test_unconfigured_is_404(env: pytest.MonkeyPatch) -> None:
    env.setenv("SOSU_GUIDEBOOK_URL", "")
    get_settings.cache_clear()
    r = _client(FakeProvider()).get("/api/v1/guidebook?t=x", follow_redirects=False)
    assert r.status_code == 404


def test_features_reports_guidebook_without_leaking_url(env: pytest.MonkeyPatch) -> None:
    c = _client(FakeProvider())
    body = c.get("/api/v1/features").json()
    assert body["guidebook"] == {"enabled": True, "reason": None}
    assert STORAGE_URL not in c.get("/api/v1/features").text
    env.setenv("SOSU_GUIDEBOOK_URL", "")
    get_settings.cache_clear()
    assert c.get("/api/v1/features").json()["guidebook"] == {
        "enabled": False,
        "reason": "guidebook_url_not_configured",
    }


def test_report_email_carries_signed_link_not_storage_url(env: pytest.MonkeyPatch) -> None:
    provider = FakeProvider()
    r = _client(provider).post("/api/v1/report-email", json=_body())
    assert r.status_code == 200, r.text
    (msg,) = provider.sent
    assert "https://api.example.test/api/v1/guidebook?t=" in msg.text
    assert "가이드북 PDF 받기" in msg.html
    assert STORAGE_URL not in msg.text and STORAGE_URL not in msg.html
    link = msg.text.split("https://api.example.test/api/v1/guidebook?t=")[1].split()[0]
    assert verify_guidebook_link(get_settings(), link) is None


def test_report_email_without_guidebook_has_no_block(env: pytest.MonkeyPatch) -> None:
    env.setenv("SOSU_GUIDEBOOK_URL", "")
    get_settings.cache_clear()
    provider = FakeProvider()
    assert _client(provider).post("/api/v1/report-email", json=_body()).status_code == 200
    sent = provider.sent[0]
    assert "/api/v1/guidebook" not in sent.text and "가이드북 PDF 받기" not in sent.html
    # No e-book block; the reel-type note may still cite the book.
    assert "전자책 PDF" not in sent.text


def test_render_escapes_link() -> None:
    report = DiagnosisReportV1.model_validate(diagnosis_report_dict())
    _, text, html = render_report_email(report, guidebook_link='https://x.test/?t=1"><b>')
    assert '"><b>' not in html
    assert "7일 동안 유효" in text


def test_email_layout_puts_guidebook_first_with_reading_guide() -> None:
    from app.email.render import GUIDEBOOK_TITLE, SPAM_NOTE

    report = DiagnosisReportV1.model_validate(diagnosis_report_dict())
    subject, text, html = render_report_email(report, guidebook_link="https://x.test/g?t=1")
    assert subject == f"[SOSU] {report.brand.name} 릴스 진단서"
    order = [
        GUIDEBOOK_TITLE,
        "이 진단 내용과 함께 보면 좋은 장",
        "한눈에 보기",
        "■ 브랜드",
        "다음 할 일",
    ]
    positions = [text.index(marker) for marker in order]
    assert positions == sorted(positions), positions
    assert html.index("가이드북 PDF 받기") < html.index("한눈에 보기") < html.index("포지셔닝</h2>")
    assert "2장 실전 릴스 유형" in text and "6장 캡션" in text
    steps = text[text.index("■ 다음 할 일") :]
    assert "1. 진단서의 30초 구성대로" in steps
    assert "2. 올린 지 3일 뒤에 인사이트 캡처 3장으로" in steps
    assert "3. 가이드북 PDF를 내려받아 읽어 보세요." in steps and "2장 '실전" not in steps
    assert SPAM_NOTE in text and escape(SPAM_NOTE) in html


def test_email_without_guidebook_has_no_reading_guide() -> None:
    report = DiagnosisReportV1.model_validate(diagnosis_report_dict())
    _, text, html = render_report_email(report)
    assert "함께 보면 좋은 장" not in text and "가이드북 PDF 받기" not in html
    assert text.index("한눈에 보기") < text.index("■ 브랜드")
    assert "가이드북 PDF를 내려받아" not in text


def test_prescription_email_layout() -> None:
    report = PrescriptionReportV1.model_validate(prescription_report_dict())
    subject, text, _ = render_report_email(report, guidebook_link="https://x.test/g?t=1")
    assert subject == "[SOSU] 릴스 처방전"
    assert text.index("SOSU 릴스 가이드북") < text.index("한눈에 보기") < text.index("■ 처방 요약")
    assert "1장 릴스의 이해" in text and "다음 릴스에서 먼저 할 것" in text


def test_subject_brand_is_single_line_and_bounded() -> None:
    data = diagnosis_report_dict()
    data["brand"]["name"] = "모노\n유리\r\nBcc: x@evil.test " + "가" * 80
    subject, _, _ = render_report_email(DiagnosisReportV1.model_validate(data))
    assert "\n" not in subject and "\r" not in subject
    assert subject.startswith("[SOSU] 모노 유리 Bcc: x@evil.test")
    assert len(subject) <= len("[SOSU]  릴스 진단서") + 40


def test_fallback_link_wraps_on_mobile() -> None:
    report = DiagnosisReportV1.model_validate(diagnosis_report_dict())
    _, _, html = render_report_email(report, guidebook_link="https://x.test/g?t=" + "a" * 90)
    fallback = html[html.index("버튼이 열리지 않으면") - 120 : html.index("버튼이 열리지 않으면")]
    assert "word-break:break-all" in fallback


def test_email_never_contains_survey_answers() -> None:
    """Footnotes list questions only; the e-mail is rendered from the report, never the answers."""
    from tests.helpers import sample_answers_dict

    report = DiagnosisReportV1.model_validate(diagnosis_report_dict())
    _, text, html = render_report_email(report, guidebook_link="https://x.test/g?t=1")
    assert "내 답" not in text and "내 답" not in html
    for value in sample_answers_dict().values():
        if isinstance(value, str) and len(value) >= 12 and value not in str(report.model_dump()):
            assert value not in text, value
