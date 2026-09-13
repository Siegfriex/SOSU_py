"""O. FastAPI endpoint contract tests (services + image normalization faked)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from app.api.deps import get_diagnosis_service, get_prescription_service
from app.contracts.diagnosis import DiagnosisReportV1
from app.contracts.envelope import ErrorCode
from app.contracts.prescription import PrescriptionReportV1
from app.domain.errors import SosuError
from app.images import normalize as image_normalize
from app.images.types import (
    ACCEPTED_IMAGE_TYPES,
    INSIGHT_IMAGE_COUNT,
    INSIGHT_IMAGE_MAX_BYTES,
    INSIGHT_IMAGES_MAX_TOTAL_BYTES,
    PRODUCT_IMAGE_MAX_BYTES,
    NormalizedImage,
)
from app.main import create_app
from fastapi.testclient import TestClient

from tests.api_samples import (
    TINY_JPEG,
    diagnosis_report_dict,
    diagnosis_request_dict,
    empty_diagnosis_request_dict,
    prescription_report_dict,
    prescription_request_dict,
)

# ------------------------------------------------------------------ fakes


class FakeDiagnosisService:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result or DiagnosisReportV1.model_validate(diagnosis_report_dict())
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def run(self, request: Any, product_image: Any, *, request_id: str) -> Any:
        self.calls.append(
            {"request": request, "product_image": product_image, "request_id": request_id}
        )
        if self.error:
            raise self.error
        return self.result


class FakePrescriptionService:
    def __init__(self, error: Exception | None = None) -> None:
        self.result = PrescriptionReportV1.model_validate(prescription_report_dict())
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def run(self, request: Any, insight_images: Any, *, request_id: str) -> Any:
        self.calls.append(
            {"request": request, "insight_images": insight_images, "request_id": request_id}
        )
        if self.error:
            raise self.error
        return self.result


def _fake_validate_upload(content_type: str | None, size_bytes: int, *, max_bytes: int) -> None:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in ACCEPTED_IMAGE_TYPES:
        raise SosuError(ErrorCode.INVALID_IMAGE_TYPE, "bad type", details=[{"content_type": ct}])
    if size_bytes > max_bytes:
        raise SosuError(ErrorCode.IMAGE_TOO_LARGE, "too large", details=[{"limit": max_bytes}])


def _fake_validate_insight_batch(sizes: list[int]) -> None:
    if len(sizes) != INSIGHT_IMAGE_COUNT:
        raise SosuError(ErrorCode.INVALID_IMAGE_COUNT, "count")
    if (
        any(s > INSIGHT_IMAGE_MAX_BYTES for s in sizes)
        or sum(sizes) > INSIGHT_IMAGES_MAX_TOTAL_BYTES
    ):
        raise SosuError(ErrorCode.IMAGE_TOO_LARGE, "too large")


def _fake_normalize(raw: bytes) -> NormalizedImage:
    return NormalizedImage(data=b"x", width=1, height=1)


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(image_normalize, "validate_upload", _fake_validate_upload)
    monkeypatch.setattr(image_normalize, "validate_insight_batch", _fake_validate_insight_batch)
    monkeypatch.setattr(image_normalize, "normalize_product_image", _fake_normalize)
    monkeypatch.setattr(image_normalize, "normalize_insight_screenshot", _fake_normalize)
    return {"diag": FakeDiagnosisService(), "pres": FakePrescriptionService()}


@pytest.fixture
def client(services: dict[str, Any]) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_diagnosis_service] = lambda: services["diag"]
    app.dependency_overrides[get_prescription_service] = lambda: services["pres"]
    return TestClient(app, raise_server_exceptions=False)


def _payload(d: dict[str, Any]) -> dict[str, str]:
    return {"payload": json.dumps(d, ensure_ascii=False)}


def _img(name: str = "p.jpg", data: bytes = TINY_JPEG, ct: str = "image/jpeg") -> tuple:
    return (name, data, ct)


def _assert_error(resp: Any, status: int, code: ErrorCode) -> dict[str, Any]:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["contract_version"] == "1.0"
    assert body["request_id"]
    assert body["error"]["code"] == code.value
    assert isinstance(body["error"]["retryable"], bool)
    assert isinstance(body["error"]["details"], list)
    return body


# ------------------------------------------------------------------ health


def test_health_shape_and_no_key_leak(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "status": "ok",
        "service": "sosu-ai",
        "contract_version": "1.0",
        "gemini_configured": body["gemini_configured"],
    }
    assert isinstance(body["gemini_configured"], bool)
    assert "key" not in r.text.lower()
    assert "PASTE_YOUR" not in r.text
    assert r.headers["X-Request-ID"]


# ------------------------------------------------------------------ diagnosis


def test_diagnosis_success_envelope(client: TestClient, services: dict[str, Any]) -> None:
    r = client.post(
        "/api/v1/diagnosis",
        data=_payload(diagnosis_request_dict()),
        headers={"X-Request-ID": "req-abc-123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["request_id"] == "req-abc-123"
    assert r.headers["X-Request-ID"] == "req-abc-123"
    assert body["contract_version"] == "1.0"
    assert body["data"]["schema_version"] == "diagnosis.v1"
    assert len(body["data"]["priorities"]) == 3
    call = services["diag"].calls[0]
    assert call["product_image"] is None
    assert call["request_id"] == "req-abc-123"
    assert call["request"].answers.q1_brand_name == "모노유리"


def test_diagnosis_with_image_passes_normalized_image(
    client: TestClient, services: dict[str, Any]
) -> None:
    r = client.post(
        "/api/v1/diagnosis",
        data=_payload(diagnosis_request_dict()),
        files={"product_image": _img()},
    )
    assert r.status_code == 200, r.text
    img = services["diag"].calls[0]["product_image"]
    assert isinstance(img, NormalizedImage)


def test_diagnosis_q19_rejected(client: TestClient) -> None:
    d = diagnosis_request_dict()
    d["answers"]["q19_anything"] = "x"
    body = _assert_error(
        client.post("/api/v1/diagnosis", data=_payload(d)), 422, ErrorCode.INVALID_REQUEST
    )
    locs = [tuple(x["loc"]) for x in body["error"]["details"]]
    assert ("answers", "q19_anything") in locs
    for detail in body["error"]["details"]:
        assert set(detail) == {"loc", "msg", "type"}


def test_diagnosis_malformed_json(client: TestClient) -> None:
    _assert_error(
        client.post("/api/v1/diagnosis", data={"payload": "{not json"}),
        422,
        ErrorCode.INVALID_REQUEST,
    )


def test_diagnosis_missing_payload_field(client: TestClient) -> None:
    _assert_error(client.post("/api/v1/diagnosis", data={}), 422, ErrorCode.INVALID_REQUEST)


def test_diagnosis_list_over_max_rejected(client: TestClient) -> None:
    d = diagnosis_request_dict()
    d["answers"]["q6_product_appeals"] = ["design", "color", "detail", "texture"]
    _assert_error(
        client.post("/api/v1/diagnosis", data=_payload(d)), 422, ErrorCode.INVALID_REQUEST
    )


def test_diagnosis_insufficient_input_without_image(client: TestClient) -> None:
    _assert_error(
        client.post("/api/v1/diagnosis", data=_payload(empty_diagnosis_request_dict())),
        422,
        ErrorCode.INSUFFICIENT_INPUT,
    )


def test_diagnosis_image_alone_is_sufficient(client: TestClient, services: dict[str, Any]) -> None:
    r = client.post(
        "/api/v1/diagnosis",
        data=_payload(empty_diagnosis_request_dict()),
        files={"product_image": _img()},
    )
    assert r.status_code == 200, r.text
    assert services["diag"].calls[0]["product_image"] is not None


def test_diagnosis_bad_mime(client: TestClient) -> None:
    _assert_error(
        client.post(
            "/api/v1/diagnosis",
            data=_payload(diagnosis_request_dict()),
            files={"product_image": _img("a.gif", b"GIF89a", "image/gif")},
        ),
        415,
        ErrorCode.INVALID_IMAGE_TYPE,
    )


def test_diagnosis_oversize_image(client: TestClient, services: dict[str, Any]) -> None:
    big = b"\xff" * (PRODUCT_IMAGE_MAX_BYTES + 1)
    _assert_error(
        client.post(
            "/api/v1/diagnosis",
            data=_payload(diagnosis_request_dict()),
            files={"product_image": _img("big.jpg", big)},
        ),
        413,
        ErrorCode.IMAGE_TOO_LARGE,
    )
    assert services["diag"].calls == []


def test_diagnosis_model_timeout_maps_to_504(client: TestClient, services: dict[str, Any]) -> None:
    services["diag"].error = SosuError(ErrorCode.MODEL_TIMEOUT, "slow")
    body = _assert_error(
        client.post("/api/v1/diagnosis", data=_payload(diagnosis_request_dict())),
        504,
        ErrorCode.MODEL_TIMEOUT,
    )
    assert body["error"]["retryable"] is True


def test_diagnosis_unhandled_exception_is_generic_500(
    client: TestClient, services: dict[str, Any]
) -> None:
    services["diag"].error = RuntimeError("SECRET-provider-stacktrace-xyz")
    body = _assert_error(
        client.post("/api/v1/diagnosis", data=_payload(diagnosis_request_dict())),
        500,
        ErrorCode.INTERNAL_ERROR,
    )
    assert "SECRET" not in json.dumps(body)
    assert body["error"]["retryable"] is False


# ------------------------------------------------------------------ prescription


def _three() -> list[tuple[str, tuple]]:
    return [("insight_images", _img(f"s{i}.jpg")) for i in range(3)]


def _post_pres(client: TestClient, d: dict[str, Any], files: list) -> Any:
    return client.post("/api/v1/prescription", data=_payload(d), files=files)


def test_prescription_success(client: TestClient, services: dict[str, Any]) -> None:
    r = client.post(
        "/api/v1/prescription", data=_payload(prescription_request_dict()), files=_three()
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["schema_version"] == "prescription.v1"
    assert len(body["data"]["next_actions"]) == 4
    call = services["pres"].calls[0]
    assert len(call["insight_images"]) == 3
    assert all(isinstance(i, NormalizedImage) for i in call["insight_images"])


@pytest.mark.parametrize("count", [2, 4])
def test_prescription_wrong_image_count(client: TestClient, count: int) -> None:
    files = [("insight_images", _img(f"s{i}.jpg")) for i in range(count)]
    _assert_error(
        client.post(
            "/api/v1/prescription", data=_payload(prescription_request_dict()), files=files
        ),
        422,
        ErrorCode.INVALID_IMAGE_COUNT,
    )


def test_prescription_no_images(client: TestClient) -> None:
    body = client.post("/api/v1/prescription", data=_payload(prescription_request_dict()))
    assert body.status_code == 422
    assert body.json()["error"]["code"] in {
        ErrorCode.INVALID_REQUEST.value,
        ErrorCode.INVALID_IMAGE_COUNT.value,
    }


def test_prescription_bad_url(client: TestClient) -> None:
    d = prescription_request_dict()
    d["instagram_url"] = "https://evil.com/reel/abc"
    _assert_error(
        client.post("/api/v1/prescription", data=_payload(d), files=_three()),
        422,
        ErrorCode.INVALID_INSTAGRAM_URL,
    )


def test_prescription_bad_mime(client: TestClient) -> None:
    files = _three()
    files[1] = ("insight_images", _img("s1.gif", b"GIF89a", "image/gif"))
    _assert_error(
        client.post(
            "/api/v1/prescription", data=_payload(prescription_request_dict()), files=files
        ),
        415,
        ErrorCode.INVALID_IMAGE_TYPE,
    )


def test_prescription_oversize_single(client: TestClient) -> None:
    files = _three()
    files[2] = ("insight_images", _img("s2.jpg", b"\xff" * (INSIGHT_IMAGE_MAX_BYTES + 1)))
    _assert_error(
        client.post(
            "/api/v1/prescription", data=_payload(prescription_request_dict()), files=files
        ),
        413,
        ErrorCode.IMAGE_TOO_LARGE,
    )


# ------------------------------------------------------------------ app-level


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == ErrorCode.INVALID_REQUEST.value


def test_cors_preflight_allowed(client: TestClient) -> None:
    r = client.options(
        "/api/v1/diagnosis",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-request-id",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_request_id_sanitized(client: TestClient) -> None:
    r = client.get("/api/v1/health", headers={"X-Request-ID": "bad id!!<script>" + "x" * 100})
    rid = r.headers["X-Request-ID"]
    assert len(rid) <= 64
    assert all(c.isalnum() or c in "._-" for c in rid)
