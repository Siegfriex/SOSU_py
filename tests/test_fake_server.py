"""Dev fake server (scripts/serve_fake.py): real pipeline + deterministic schema-aware gateway."""

from __future__ import annotations

import json
from typing import Any

import pytest
from app.api.deps import _build_gateway, get_gateway
from app.main import create_app
from fastapi.testclient import TestClient
from scripts.fake_gateway import SCENARIOS
from scripts.serve_fake import build_fake_app

from tests.api_samples import TINY_JPEG, diagnosis_request_dict, prescription_request_dict


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_fake_app())


def _diagnosis(client: TestClient, *, image: bool = True, headers: Any = None) -> Any:
    files: dict[str, Any] = {"payload": (None, json.dumps(diagnosis_request_dict()))}
    if image:
        files["product_image"] = ("p.jpg", TINY_JPEG, "image/jpeg")
    return client.post("/api/v1/diagnosis", files=files, headers=headers or {})


def _prescription(client: TestClient, *, n: int = 3, headers: Any = None) -> Any:
    files: list[tuple[str, Any]] = [
        ("payload", (None, json.dumps(prescription_request_dict()))),
        *[("insight_images", (f"i{i}.jpg", TINY_JPEG, "image/jpeg")) for i in range(n)],
    ]
    return client.post("/api/v1/prescription", files=files, headers=headers or {})


def test_repeated_success_both_endpoints(client: TestClient) -> None:
    for _ in range(3):
        r = _diagnosis(client)
        assert r.status_code == 200, r.text
        assert r.headers["x-sosu-fake"] == "1"
        data = r.json()["data"]
        assert data["brand"]["name"] == "모노유리"
        assert len(data["priorities"]) == 3
        r = _diagnosis(client, image=False)
        assert r.status_code == 200
        r = _prescription(client)
        assert r.status_code == 200, r.text
        assert len(r.json()["data"]["next_actions"]) == 4


EXPECTED = {
    "timeout": (504, "MODEL_TIMEOUT"),
    "provider_error": (502, "MODEL_PROVIDER_ERROR"),
    "schema_error": (502, "MODEL_SCHEMA_ERROR"),
    "repair_failed": (502, "REPAIR_FAILED"),
    "fatal_content": (502, "MODEL_CONTENT_ERROR"),
}


@pytest.mark.parametrize("scenario", sorted(EXPECTED))
@pytest.mark.parametrize("endpoint", ["diagnosis", "prescription"])
def test_error_scenarios_via_control_endpoint(
    client: TestClient, scenario: str, endpoint: str
) -> None:
    r = client.post("/__fake__/scenario", json={"scenario": scenario, "times": 1})
    assert r.status_code == 200 and r.json()["remaining"] == 1
    call = _diagnosis if endpoint == "diagnosis" else _prescription
    r = call(client)
    status, code = EXPECTED[scenario]
    assert r.status_code == status, r.text
    body = r.json()
    assert body["ok"] is False and body["error"]["code"] == code
    assert body["error"]["retryable"] is True
    # queue consumed → next request succeeds
    assert call(client).status_code == 200


@pytest.mark.parametrize("endpoint", ["diagnosis", "prescription"])
def test_repairable_scenario_succeeds_after_repair(client: TestClient, endpoint: str) -> None:
    r = (
        _diagnosis(client, headers={"X-SOSU-Fake-Scenario": "repairable"})
        if (endpoint == "diagnosis")
        else _prescription(client, headers={"X-SOSU-Fake-Scenario": "repairable"})
    )
    assert r.status_code == 200, r.text
    calls = client.app.state.fake.gateway.calls  # type: ignore[attr-defined]
    assert calls[-1].prompt_version == "repair-v1"


def test_header_scenario_and_slow(client: TestClient) -> None:
    r = _diagnosis(client, headers={"X-SOSU-Fake-Scenario": "timeout"})
    assert r.status_code == 504
    r = _diagnosis(client, headers={"X-SOSU-Fake-Scenario": "slow:0.05"})
    assert r.status_code == 200


def test_validation_errors_are_real_and_do_not_consume_queue(client: TestClient) -> None:
    client.post("/__fake__/scenario", json={"scenario": "timeout", "times": 1})
    empty = {"contract_version": "1.0", "locale": "ko-KR", "answers": {}}
    r = client.post("/api/v1/diagnosis", files={"payload": (None, json.dumps(empty))})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INSUFFICIENT_INPUT"
    r = client.post("/api/v1/diagnosis", files={"payload": (None, "{not json")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    r = _prescription(client, n=2)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_IMAGE_COUNT"
    files = {
        "payload": (None, json.dumps(diagnosis_request_dict())),
        "product_image": ("p.gif", b"GIF89a....", "image/gif"),
    }
    r = client.post("/api/v1/diagnosis", files=files)
    assert r.status_code == 415 and r.json()["error"]["code"] == "INVALID_IMAGE_TYPE"
    assert client.get("/__fake__/scenario").json()["remaining"] == 1
    assert _diagnosis(client).status_code == 504


def test_control_endpoints_and_last_request(client: TestClient) -> None:
    assert client.get("/__fake__/scenario").json()["available"] == list(SCENARIOS)
    assert client.post("/__fake__/scenario", json={"scenario": "nope"}).status_code == 422
    _diagnosis(client)
    last = client.get("/__fake__/last-request").json()
    assert last["endpoint"] == "/api/v1/diagnosis"
    assert last["payload"]["answers"]["q18_disclosure"] == "face_only"
    assert last["files"] == [
        {
            "field": "product_image",
            "filename": "p.jpg",
            "content_type": "image/jpeg",
            "size_bytes": len(TINY_JPEG),
        }
    ]
    assert last["request_id"]
    _prescription(client)
    assert len(client.get("/__fake__/last-request?all=1").json()) == 2
    client.post("/__fake__/scenario", json={"scenario": "timeout", "times": 3})
    reset = client.post("/__fake__/reset").json()
    assert reset["remaining"] == 0
    assert client.get("/__fake__/last-request").json() is None


def test_production_app_has_no_fake_surface() -> None:
    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any(p.startswith("/__fake__") for p in paths)
    assert get_gateway not in app.dependency_overrides
    assert get_gateway.__module__ == "app.api.deps"
    assert _build_gateway.__module__ == "app.api.deps"
    with TestClient(app) as c:
        r = c.get("/api/v1/health")
        assert "x-sosu-fake" not in r.headers
    import app.main as main_module

    src = open(main_module.__file__, encoding="utf-8").read()  # noqa: SIM115
    assert "fake" not in src.lower()
