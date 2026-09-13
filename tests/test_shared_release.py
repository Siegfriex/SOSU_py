"""Shared contract release (<monorepo>/contracts/) must validate against the runtime models.

The release is rendered in-process into a tmp dir so the suite is self-contained; when the real
release directory exists it is additionally checked for staleness.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from app.contracts.catalog import CATALOG_ENUM_TYPES, catalog_as_json
from app.contracts.diagnosis import DiagnosisReportV1, SurveyDiagnosisRequestV1
from app.contracts.envelope import ErrorCode, ErrorEnvelope, SuccessEnvelope
from app.contracts.prescription import PrescriptionReportV1, PrescriptionRequestV1
from app.domain.errors import SosuError
from app.main import create_app
from scripts.release_shared_contract import (
    ARTIFACTS,
    DIAGNOSIS_ERROR_CODES,
    PRESCRIPTION_ERROR_CODES,
    QUESTION_FIELDS,
    check_release,
    default_out_dir,
    write_release,
)


@pytest.fixture(scope="module")
def release_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("shared_contracts")
    write_release(out)
    return out


def _json(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ shape


def test_release_has_exactly_three_artifacts(release_dir: Path) -> None:
    assert sorted(p.name for p in release_dir.iterdir()) == sorted(ARTIFACTS)


def test_write_refuses_directory_with_foreign_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("x")
    with pytest.raises(SystemExit):
        write_release(tmp_path)


# ------------------------------------------------------------------ 02_openapi.json


def test_openapi_artifact_equals_runtime(release_dir: Path) -> None:
    assert _json(release_dir / "02_openapi.json") == create_app().openapi()


# ------------------------------------------------------------------ 03_CONTRACT_FIXTURES.json


def test_fixture_projection_has_required_keys(release_dir: Path) -> None:
    fx = _json(release_dir / "03_CONTRACT_FIXTURES.json")
    for wf in ("diagnosis", "prescription"):
        assert set(fx[wf]) >= {"endpoint", "request", "success", "errors"}
        assert set(fx[wf]["errors"]) == {"retryable", "non_retryable"}
    assert "ui_option_catalog" in fx
    assert fx["contract_version"] == "1.0"


def test_fixture_requests_validate(release_dir: Path) -> None:
    fx = _json(release_dir / "03_CONTRACT_FIXTURES.json")
    d = SurveyDiagnosisRequestV1.model_validate(fx["diagnosis"]["request"])
    assert d.answers.q18_disclosure is not None
    p = PrescriptionRequestV1.model_validate(fx["prescription"]["request"])
    assert "/reel/" in p.instagram_url


def test_fixture_success_envelopes_validate(release_dir: Path) -> None:
    fx = _json(release_dir / "03_CONTRACT_FIXTURES.json")
    d = SuccessEnvelope[DiagnosisReportV1].model_validate(fx["diagnosis"]["success"])
    assert d.ok is True and d.data.schema_version == "diagnosis.v1"
    assert d.model_dump(mode="json") == fx["diagnosis"]["success"]
    p = SuccessEnvelope[PrescriptionReportV1].model_validate(fx["prescription"]["success"])
    assert p.ok is True and len(p.data.next_actions) == 4
    assert p.model_dump(mode="json") == fx["prescription"]["success"]


@pytest.mark.parametrize(
    "wf,codes", [("diagnosis", DIAGNOSIS_ERROR_CODES), ("prescription", PRESCRIPTION_ERROR_CODES)]
)
def test_fixture_error_groups_validate_and_match_retryable_flag(
    release_dir: Path, wf: str, codes: frozenset[ErrorCode]
) -> None:
    fx = _json(release_dir / "03_CONTRACT_FIXTURES.json")
    seen: set[ErrorCode] = set()
    for bucket, expected_flag in (("retryable", True), ("non_retryable", False)):
        for code_str, payload in fx[wf]["errors"][bucket].items():
            env = ErrorEnvelope.model_validate(payload)
            assert env.ok is False
            assert env.error.code.value == code_str
            assert env.error.retryable is expected_flag
            # retryable flag in the fixture equals the runtime default for that code
            assert SosuError(env.error.code, "x").retryable is expected_flag
            assert env.request_id.startswith(f"fixture-{wf}-")
            seen.add(env.error.code)
    assert seen == codes, f"{wf}: fixture error coverage differs from declared codes"


def test_every_error_code_appears_in_some_workflow(release_dir: Path) -> None:
    assert DIAGNOSIS_ERROR_CODES | PRESCRIPTION_ERROR_CODES == set(ErrorCode)


def test_fixture_catalog_matches_runtime(release_dir: Path) -> None:
    fx = _json(release_dir / "03_CONTRACT_FIXTURES.json")
    assert fx["ui_option_catalog"] == json.loads(json.dumps(catalog_as_json()))
    assert any(
        o["label"] == "사진/영상 혼합" and o["code"] == "photo_video_mix"
        for o in fx["ui_option_catalog"]["questions"]["q17"]["options"]
    )


# ------------------------------------------------------------------ 01_DOMAIN_CONTRACT.md


def test_domain_contract_mentions_every_runtime_name(release_dir: Path) -> None:
    md = (release_dir / "01_DOMAIN_CONTRACT.md").read_text(encoding="utf-8")
    for _, field, _, _ in QUESTION_FIELDS:
        assert f"`{field}`" in md, field
    assert "q19" in md.lower()
    for code in ErrorCode:
        assert f"`{code.value}`" in md, code
    for enum_type in set(CATALOG_ENUM_TYPES.values()):
        for member in enum_type:
            assert f"`{member.value}`" in md, member
    for path in ("/api/v1/health", "/api/v1/diagnosis", "/api/v1/prescription"):
        assert path in md
    assert "EvidencePack" in md  # boundary section
    assert re.search(r"180s", md) and "45s" in md and "90s" in md and "40s" in md
    assert "PDF" in md and "/p/" in md


def test_domain_contract_does_not_use_ssot_legacy_wire_names(release_dir: Path) -> None:
    md = (release_dir / "01_DOMAIN_CONTRACT.md").read_text(encoding="utf-8")
    for legacy in (
        "appeal_codes",
        "exposure_mode",
        "brand_summary",
        "first_show_priorities",
        "INPUT_INVALID",
        "face_and_voice",
        "making_process",
    ):
        assert legacy not in md, legacy


# ------------------------------------------------------------------ real release dir (if present)


def test_real_shared_release_is_current_when_present() -> None:
    out = default_out_dir()
    if not out.exists():
        pytest.skip(f"shared release not generated yet: {out}")
    problems = check_release(out)
    assert not problems, (
        "\n".join(problems) + "\n→ uv run python scripts/release_shared_contract.py"
    )
