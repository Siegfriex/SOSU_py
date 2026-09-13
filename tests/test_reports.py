"""J. DiagnosisReportV1 validation, K. PrescriptionReportV1 / PrescriptionRequestV1 validation."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from app.contracts.diagnosis import DiagnosisReportV1
from app.contracts.prescription import (
    PrescriptionReportV1,
    PrescriptionRequestV1,
    is_valid_instagram_reel_url,
)
from pydantic import ValidationError

# ------------------------------------------------------------------ J. DiagnosisReportV1


def test_diagnosis_report_valid_sample(sample_diagnosis_report_dict: dict[str, Any]) -> None:
    report = DiagnosisReportV1.model_validate(sample_diagnosis_report_dict)
    assert report.schema_version == "diagnosis.v1"
    assert [p.rank for p in report.priorities] == [1, 2, 3]
    assert len(report.reel_types) == 3
    # round-trip is lossless
    assert report.model_dump(mode="json") == sample_diagnosis_report_dict


@pytest.mark.parametrize("count", [2, 4])
def test_diagnosis_priorities_must_be_exactly_three(
    sample_diagnosis_report_dict: dict[str, Any], count: int
) -> None:
    data = copy.deepcopy(sample_diagnosis_report_dict)
    items = data["priorities"]
    data["priorities"] = (items * 2)[:count]
    with pytest.raises(ValidationError):
        DiagnosisReportV1.model_validate(data)


def test_diagnosis_priority_rank_4_rejected(sample_diagnosis_report_dict: dict[str, Any]) -> None:
    data = copy.deepcopy(sample_diagnosis_report_dict)
    data["priorities"][2]["rank"] = 4
    with pytest.raises(ValidationError):
        DiagnosisReportV1.model_validate(data)


@pytest.mark.parametrize("count", [2, 4])
def test_diagnosis_reel_types_must_be_exactly_three(
    sample_diagnosis_report_dict: dict[str, Any], count: int
) -> None:
    data = copy.deepcopy(sample_diagnosis_report_dict)
    data["reel_types"] = (data["reel_types"] * 2)[:count]
    with pytest.raises(ValidationError):
        DiagnosisReportV1.model_validate(data)


@pytest.mark.parametrize("key", ["hook_0_3", "body_3_10", "body_10_20", "close_20_27", "cta_27_30"])
def test_diagnosis_structure_keys_required(
    sample_diagnosis_report_dict: dict[str, Any], key: str
) -> None:
    data = copy.deepcopy(sample_diagnosis_report_dict)
    del data["structure"][key]
    with pytest.raises(ValidationError):
        DiagnosisReportV1.model_validate(data)


def test_diagnosis_wrong_schema_version(sample_diagnosis_report_dict: dict[str, Any]) -> None:
    data = copy.deepcopy(sample_diagnosis_report_dict)
    data["schema_version"] = "diagnosis.v2"
    with pytest.raises(ValidationError):
        DiagnosisReportV1.model_validate(data)


def test_diagnosis_extra_field_rejected(sample_diagnosis_report_dict: dict[str, Any]) -> None:
    data = copy.deepcopy(sample_diagnosis_report_dict)
    data["chain_of_thought"] = "..."
    with pytest.raises(ValidationError):
        DiagnosisReportV1.model_validate(data)


@pytest.mark.parametrize("section", ["strengths", "final_guidance"])
def test_diagnosis_empty_lists_rejected(
    sample_diagnosis_report_dict: dict[str, Any], section: str
) -> None:
    data = copy.deepcopy(sample_diagnosis_report_dict)
    data[section] = []
    with pytest.raises(ValidationError):
        DiagnosisReportV1.model_validate(data)


def test_diagnosis_missing_section_rejected(
    sample_diagnosis_report_dict: dict[str, Any],
) -> None:
    for section in ("brand", "positioning", "target", "tone", "fonts", "structure"):
        data = copy.deepcopy(sample_diagnosis_report_dict)
        del data[section]
        with pytest.raises(ValidationError):
            DiagnosisReportV1.model_validate(data)


# ------------------------------------------------------------------ K. PrescriptionReportV1


def test_prescription_report_valid_sample(
    sample_prescription_report_dict: dict[str, Any],
) -> None:
    report = PrescriptionReportV1.model_validate(sample_prescription_report_dict)
    assert report.schema_version == "prescription.v1"
    assert [a.order for a in report.next_actions] == [1, 2, 3, 4]
    assert report.model_dump(mode="json") == sample_prescription_report_dict


@pytest.mark.parametrize("count", [3, 5])
def test_prescription_next_actions_exactly_four(
    sample_prescription_report_dict: dict[str, Any], count: int
) -> None:
    data = copy.deepcopy(sample_prescription_report_dict)
    data["next_actions"] = (data["next_actions"] * 2)[:count]
    with pytest.raises(ValidationError):
        PrescriptionReportV1.model_validate(data)


def test_prescription_order_5_rejected(sample_prescription_report_dict: dict[str, Any]) -> None:
    data = copy.deepcopy(sample_prescription_report_dict)
    data["next_actions"][3]["order"] = 5
    with pytest.raises(ValidationError):
        PrescriptionReportV1.model_validate(data)


def test_prescription_wrong_schema_version(
    sample_prescription_report_dict: dict[str, Any],
) -> None:
    data = copy.deepcopy(sample_prescription_report_dict)
    data["schema_version"] = "diagnosis.v1"
    with pytest.raises(ValidationError):
        PrescriptionReportV1.model_validate(data)


def test_prescription_extra_field_rejected(
    sample_prescription_report_dict: dict[str, Any],
) -> None:
    data = copy.deepcopy(sample_prescription_report_dict)
    data["raw_model_text"] = "..."
    with pytest.raises(ValidationError):
        PrescriptionReportV1.model_validate(data)


# ------------------------------------------------------------------ K. PrescriptionRequestV1 URL


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/reel/C0ffee123AB/",
        "https://www.instagram.com/reel/C0ffee123AB",
        "https://instagram.com/reels/Abc_-123",
        "https://m.instagram.com/reel/Abc123/",
        "https://www.instagram.com/reel/C0ffee123AB/?igsh=abc123",
        "  https://www.instagram.com/reel/C0ffee123AB/  ",
        "http://www.instagram.com/reel/C0ffee123AB/",
    ],
)
def test_valid_instagram_urls(url: str) -> None:
    req = PrescriptionRequestV1(instagram_url=url)
    assert req.instagram_url == url.strip()
    assert is_valid_instagram_reel_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/monoyuri/",
        "https://www.instagram.com/p/C0ffee123AB/",  # owner decision: /p/ posts rejected in v1
        "https://www.instagram.com/p/C0ffee123AB",
        "https://www.instagram.com/tv/C0ffee123AB/",
        "https://www.instagram.com/monoyuri/reel/C0ffee123AB/",
        "https://www.instagram.com/reel/C0ffee123AB/extra/",
        "https://www.instagram.com/",
        "http://evil.com/reel/abc",
        "https://instagram.com.evil.com/reel/abc",
        "https://www.instagram.com/reel/",
        "https://www.instagram.com/stories/monoyuri/123/",
        "ftp://www.instagram.com/reel/abc",
        "not a url",
        "",
        "javascript:alert(1)",
    ],
)
def test_invalid_instagram_urls(url: str) -> None:
    assert not is_valid_instagram_reel_url(url)
    with pytest.raises(ValidationError) as exc:
        PrescriptionRequestV1(instagram_url=url)
    assert "INVALID_INSTAGRAM_URL" in str(exc.value)


def test_prescription_request_rejects_extra_and_wrong_version(
    sample_prescription_request: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        PrescriptionRequestV1.model_validate({**sample_prescription_request, "email": "x@y.z"})
    with pytest.raises(ValidationError):
        PrescriptionRequestV1.model_validate(
            {**sample_prescription_request, "contract_version": "0.9"}
        )
