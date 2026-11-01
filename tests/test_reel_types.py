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


def test_email_moves_question_refs_to_footnote_and_adds_guidebook_note():
    from app.email.render import render_report_email, strip_refs

    assert strip_refs("BGM을 깝니다(q4, q15).") == ("BGM을 깝니다.", [4, 15])
    assert strip_refs("q17 답변처럼 (q99)") == ("17번 문항 답변처럼 (q99)", [17])
    d = diagnosis_draft_dict()
    d["reel_types"][1]["reason"] = "작업 소리가 약해 보여 BGM을 깝니다(q4, q15)."
    report = to_public_diagnosis(sample_diagnosis_draft(**d), voice_allowed=True)
    _, text, html = render_report_email(report)
    assert "(q4, q15)" not in text and "q15" not in html
    assert "근거 질문" in text and "15. 사람들이 보면 신기해할 만한 제작 과정이 있나요?" in text
    assert "4. 주로 어떤 소재를 사용하나요?" in html
    assert "*릴스 유형은 가이드북 2장 '실전 릴스 유형' 참고" in text
