"""Guidebook reel types (A~F): one code per axis, fixed public names, Q18-safe labels."""

from __future__ import annotations

import pytest
from app.contracts.enums import CreatorDisclosure
from app.domain.evidence import CreatorConstraint
from app.domain.reel_types import axis_errors, code_of_name, combination, reel_type_name
from app.domain.validator import ValidationOutcome, validate_diagnosis
from app.gemini.schemas import gemini_json_schema, to_public_diagnosis
from pydantic import ValidationError

from tests.fakes import diagnosis_draft_dict, sample_diagnosis_draft


def _draft(codes: tuple[str, str, str]):
    d = diagnosis_draft_dict()
    for item, code in zip(d["reel_types"], codes, strict=True):
        item["code"] = code
    return sample_diagnosis_draft(**d)


def test_schema_constrains_code_to_guidebook_letters():
    schema = gemini_json_schema(type(sample_diagnosis_draft()))
    code = schema["$defs"]["ReelTypeDraft"]["properties"]["code"]
    assert code["enum"] == ["A", "B", "C", "D", "E", "F"]


def test_free_text_code_is_rejected():
    with pytest.raises(ValidationError):
        _draft(("제작 디테일형", "D", "F"))


@pytest.mark.parametrize("codes", [("A", "C", "E"), ("B", "D", "F"), ("F", "B", "C")])
def test_one_per_axis_passes(codes):
    report = validate_diagnosis(_draft(codes), CreatorConstraint.from_disclosure(None))
    assert report.outcome is ValidationOutcome.PASS, report.errors


@pytest.mark.parametrize("codes", [("A", "B", "F"), ("B", "D", "C"), ("E", "F", "A")])
def test_two_from_one_axis_is_repairable(codes):
    report = validate_diagnosis(_draft(codes), CreatorConstraint.from_disclosure(None))
    assert report.outcome is ValidationOutcome.REPAIRABLE
    assert any(e.startswith("reel_types:") for e in report.errors)


def test_public_names_are_fixed_labels_in_axis_order():
    report = to_public_diagnosis(_draft(("F", "B", "D")), voice_allowed=True)
    assert [r.name for r in report.reel_types] == [
        "유형 B · 완성된 제품을 먼저",
        "유형 D · 사운드가 약할 경우",
        "유형 F · 자막이나 나레이션이 있는 경우",
    ]
    assert combination([code_of_name(r.name) or "" for r in report.reel_types]) == "B+D+F"


@pytest.mark.parametrize("disc", [CreatorDisclosure.NO, CreatorDisclosure.FACE_ONLY])
def test_voice_free_creator_never_sees_narration_and_still_passes(disc):
    constraint = CreatorConstraint.from_disclosure(disc)
    draft = _draft(("B", "D", "F"))
    assert validate_diagnosis(draft, constraint).outcome is ValidationOutcome.PASS
    report = to_public_diagnosis(draft, voice_allowed=constraint.voice_allowed)
    names = " ".join(r.name for r in report.reel_types)
    assert "나레이션" not in names
    assert report.reel_types[2].name == "유형 F · 자막이 있는 경우"


def test_helpers():
    assert reel_type_name("E", voice_allowed=False) == "유형 E · 자막이 없는 경우"
    assert code_of_name("제작 디테일형") is None
    assert axis_errors(["A", "C", "E"]) == []
    assert len(axis_errors(["A", "B", "C"])) == 2


def test_email_shows_combination_line():
    from app.email.render import render_report_email

    report = to_public_diagnosis(_draft(("B", "D", "F")), voice_allowed=True)
    _, text, html = render_report_email(report)
    assert "추천 조합: B+D+F" in text and "추천 조합: B+D+F" in html
    assert "유형 B · 완성된 제품을 먼저" in text
