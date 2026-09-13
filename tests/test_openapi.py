"""P. Exported OpenAPI/fixtures must match the runtime models exactly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.contracts.diagnosis import DiagnosisReportV1, SurveyDiagnosisRequestV1
from app.contracts.envelope import ErrorCode, ErrorEnvelope, SuccessEnvelope
from app.contracts.prescription import PrescriptionReportV1, PrescriptionRequestV1
from app.domain.errors import SosuError
from scripts.export_openapi import OPENAPI_PATH, render_openapi

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contracts" / "fixtures"
README = ROOT / "contracts" / "README.md"

STALE_MSG = (
    "contracts/openapi.json does not match the runtime app. "
    "Run: uv run python scripts/export_openapi.py"
)


def test_openapi_file_matches_runtime() -> None:
    assert OPENAPI_PATH.exists(), STALE_MSG
    assert OPENAPI_PATH.read_text(encoding="utf-8") == render_openapi(), STALE_MSG


def test_openapi_paths_and_multipart_fields() -> None:
    spec = json.loads(render_openapi())
    paths = spec["paths"]
    assert set(paths) == {"/api/v1/health", "/api/v1/diagnosis", "/api/v1/prescription"}
    assert "get" in paths["/api/v1/health"]

    def multipart_props(path: str) -> dict:
        body = paths[path]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
        ref = body["$ref"].rsplit("/", 1)[-1]
        return spec["components"]["schemas"][ref]["properties"]

    diag = multipart_props("/api/v1/diagnosis")
    assert set(diag) == {"payload", "product_image"}
    assert diag["payload"]["type"] == "string"

    pres = multipart_props("/api/v1/prescription")
    assert set(pres) == {"payload", "insight_images"}
    assert pres["insight_images"]["type"] == "array"

    for path in ("/api/v1/diagnosis", "/api/v1/prescription"):
        responses = paths[path]["post"]["responses"]
        for status in ("413", "415", "422", "500", "502", "504"):
            ref = responses[status]["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/ErrorEnvelope")

    schemas = spec["components"]["schemas"]
    assert "DiagnosisReportV1" in schemas and "PrescriptionReportV1" in schemas
    for name in ("SurveyDiagnosisRequestV1", "SurveyAnswersV1", "PrescriptionRequestV1"):
        assert name in schemas, f"{name} must be exported for the payload text field"
    props = schemas["SurveyAnswersV1"]["properties"]
    assert not any(k.startswith("q19") for k in props)
    assert len(props) == 19  # q1..q18 + q20
    assert schemas["SurveyAnswersV1"]["additionalProperties"] is False
    assert spec["x-payload-models"]["/api/v1/diagnosis"].endswith("SurveyDiagnosisRequestV1")
    for enum_name in (
        "ProductAppeal",
        "PurchaseMotive",
        "DesiredEmotion",
        "BrandAttribute",
        "InstagramPainPoint",
        "CurrentReelFormat",
        "CreatorDisclosure",
    ):
        assert enum_name in schemas


def test_openapi_error_code_enum_complete() -> None:
    spec = json.loads(render_openapi())
    assert set(spec["components"]["schemas"]["ErrorCode"]["enum"]) == {c.value for c in ErrorCode}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_request_fixtures_validate() -> None:
    req = SurveyDiagnosisRequestV1.model_validate(_load("diagnosis.request.json"))
    assert req.answers.q18_disclosure == "face_only"
    assert req.model_dump(mode="json") == _load("diagnosis.request.json")
    pres = PrescriptionRequestV1.model_validate(_load("prescription.request.json"))
    assert pres.model_dump(mode="json") == _load("prescription.request.json")


def test_success_fixtures_validate() -> None:
    d = SuccessEnvelope[DiagnosisReportV1].model_validate(_load("diagnosis.success.json"))
    assert d.ok is True and d.data.schema_version == "diagnosis.v1"
    assert d.model_dump(mode="json") == _load("diagnosis.success.json")
    p = SuccessEnvelope[PrescriptionReportV1].model_validate(_load("prescription.success.json"))
    assert p.data.schema_version == "prescription.v1"
    assert p.model_dump(mode="json") == _load("prescription.success.json")


def test_diagnosis_fixture_respects_face_only_constraint() -> None:
    data = _load("diagnosis.success.json")["data"]
    texts = json.dumps(
        [data["priorities"], data["reel_types"], data["structure"], data["final_guidance"]],
        ensure_ascii=False,
    )
    for forbidden in ("내레이션", "나레이션", "보이스오버", "voice-over", "narration"):
        assert forbidden not in texts


@pytest.mark.parametrize("path", sorted(p.name for p in FIXTURES.glob("error.*.json")))
def test_error_fixtures_validate(path: str) -> None:
    env = ErrorEnvelope.model_validate(_load(path))
    assert env.ok is False
    assert env.error.code in set(ErrorCode)
    expected = SosuError(env.error.code, "x")
    if env.error.code is not ErrorCode.INTERNAL_ERROR:
        assert env.error.retryable == expected.retryable
    assert env.model_dump(mode="json") == _load(path)


def test_every_error_code_documented() -> None:
    fixture_codes = {_load(p.name)["error"]["code"] for p in FIXTURES.glob("error.*.json")}
    readme = README.read_text(encoding="utf-8")
    for code in ErrorCode:
        assert code.value in fixture_codes or f"`{code.value}`" in readme, code
        assert f"`{code.value}`" in readme, f"{code} missing from contracts/README.md table"
        err = SosuError(code, "x")
        assert f"| `{code.value}` | {err.http_status} | {str(err.retryable).lower()} |" in readme


def test_fixture_dir_has_required_files() -> None:
    required = {
        "diagnosis.request.json",
        "diagnosis.success.json",
        "prescription.request.json",
        "prescription.success.json",
        "error.invalid_request.json",
        "error.insufficient_input.json",
        "error.invalid_image_type.json",
        "error.image_too_large.json",
        "error.invalid_image_count.json",
        "error.invalid_instagram_url.json",
        "error.model_timeout.json",
        "error.repair_failed.json",
        "error.internal_error.json",
    }
    assert required <= {p.name for p in FIXTURES.glob("*.json")}
