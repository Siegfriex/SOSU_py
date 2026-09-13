"""D. Q18 derivation, E. natural language untouched, F. Q19 rejected, G. list caps."""

from __future__ import annotations

import unicodedata

import pytest
from app.contracts.diagnosis import MAX_CHOICES, SurveyAnswersV1, SurveyDiagnosisRequestV1
from app.contracts.enums import CreatorDisclosure, ProductAppeal
from app.domain.evidence import CreatorConstraint
from app.domain.normalizer import (
    LIST_FIELDS,
    SAFE_MAX_TEXT_LEN,
    TEXT_FIELDS,
    normalize_survey,
    normalize_text,
)
from pydantic import ValidationError

# ------------------------------------------------------------------ D. Q18 → constraint


@pytest.mark.parametrize(
    ("disclosure", "face", "voice"),
    [
        (CreatorDisclosure.YES, True, True),
        (CreatorDisclosure.NO, False, False),
        (CreatorDisclosure.FACE_ONLY, True, False),
        (CreatorDisclosure.VOICE_ONLY, False, True),
    ],
)
def test_creator_constraint_derivation(
    disclosure: CreatorDisclosure, face: bool, voice: bool
) -> None:
    c = CreatorConstraint.from_disclosure(disclosure)
    assert (c.face_allowed, c.voice_allowed, c.source) == (face, voice, disclosure)


def test_creator_constraint_none_is_unconstrained() -> None:
    c = CreatorConstraint.from_disclosure(None)
    assert (c.face_allowed, c.voice_allowed, c.source) == (True, True, None)


def test_normalize_survey_carries_constraint(sample_answers: dict) -> None:
    declared = normalize_survey(SurveyAnswersV1.model_validate(sample_answers))
    assert declared.q18_disclosure is CreatorDisclosure.FACE_ONLY
    assert declared.creator_constraint.face_allowed is True
    assert declared.creator_constraint.voice_allowed is False
    assert "q18" in declared.answered_question_ids


# ------------------------------------------------------------------ E. natural language untouched

RICH_TEXT = (
    "다른 데는 보통 파스텔 조합만 하는데, 저는 일부러 투명한 거랑  탁한 색을 섞어요!\n"
    "같은 조합도 조금씩 다르게 만들어요… “완전 똑같은 건” 거의 없어요 ✨🧵\n"
    "\n"
    "Q: 왜요? A: 그게 '손맛'이니까요 (진짜로)."
)


def test_rich_text_survives_exactly() -> None:
    assert normalize_text(RICH_TEXT) == RICH_TEXT


def test_only_trim_crlf_nfc_are_applied() -> None:
    raw = "  \r\n" + RICH_TEXT.replace("\n", "\r\n") + "   \r\n\r\n"
    assert normalize_text(raw) == RICH_TEXT


def test_double_spaces_inside_a_line_are_preserved() -> None:
    assert normalize_text("투명한 거랑  탁한 색") == "투명한 거랑  탁한 색"


def test_nfd_input_becomes_nfc() -> None:
    nfd = unicodedata.normalize("NFD", "별빛, 물결")
    assert nfd != "별빛, 물결"
    assert normalize_text(nfd) == "별빛, 물결"


def test_excessive_blank_lines_collapse_but_single_blank_line_kept() -> None:
    assert normalize_text("a\n\n\n\n\nb") == "a\n\nb"
    assert normalize_text("a\n\nb") == "a\n\nb"


@pytest.mark.parametrize("raw", ["", "   ", "\r\n\t ", None])
def test_empty_becomes_none(raw: str | None) -> None:
    assert normalize_text(raw) is None


def test_overlong_text_is_truncated_prefix() -> None:
    raw = "가" * (SAFE_MAX_TEXT_LEN + 500)
    out = normalize_text(raw)
    assert out is not None
    assert len(out) <= SAFE_MAX_TEXT_LEN
    assert raw.startswith(out)


def test_normalize_survey_does_not_rewrite_text(sample_answers: dict) -> None:
    declared = normalize_survey(SurveyAnswersV1.model_validate(sample_answers))
    for name in TEXT_FIELDS:
        assert getattr(declared, name) == sample_answers[name].strip(), name


def test_normalize_survey_answered_ids(sample_answers: dict) -> None:
    declared = normalize_survey(SurveyAnswersV1.model_validate(sample_answers))
    expected = {f"q{n}" for n in range(1, 21) if n != 19}
    assert set(declared.answered_question_ids) == expected
    assert declared.has_meaningful_answer


def test_normalize_empty_survey_has_no_meaningful_answer() -> None:
    declared = normalize_survey(SurveyAnswersV1(q1_brand_name="   "))
    assert declared.answered_question_ids == []
    assert not declared.has_meaningful_answer


# ------------------------------------------------------------------ F. Q19 must not exist


@pytest.mark.parametrize("name", ["q19", "q19_anything", "q19_reference_accounts"])
def test_q19_field_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError) as exc:
        SurveyAnswersV1.model_validate({name: "x"})
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_q19_not_in_schema() -> None:
    assert not any(k.startswith("q19") for k in SurveyAnswersV1.model_fields)
    assert not any(k.startswith("q19") for k in SurveyAnswersV1.model_json_schema()["properties"])


def test_request_rejects_extra_top_level_key(sample_answers: dict) -> None:
    with pytest.raises(ValidationError):
        SurveyDiagnosisRequestV1.model_validate({"answers": sample_answers, "email": "a@b.c"})


def test_request_rejects_wrong_contract_version(sample_answers: dict) -> None:
    with pytest.raises(ValidationError):
        SurveyDiagnosisRequestV1.model_validate(
            {"contract_version": "2.0", "answers": sample_answers}
        )


def test_request_accepts_partial_answers() -> None:
    req = SurveyDiagnosisRequestV1.model_validate({"answers": {"q3_hero_product": "유리 키링"}})
    assert req.contract_version == "1.0"
    assert req.locale == "ko-KR"


# ------------------------------------------------------------------ G. list caps

_FOUR: dict[str, list[str]] = {
    "q6_product_appeals": ["design", "color", "detail", "texture"],
    "q9_purchase_motives": ["aesthetic", "specialness", "self_reward", "gift"],
    "q10_desired_emotions": ["excitement", "happiness", "warmth", "healing"],
    "q11_brand_attributes": ["excitement", "happiness", "warmth", "healing"],
    "q16_pain_points": ["low_reach", "low_follower_growth", "ideation", "shooting_difficulty"],
    "q17_current_formats": ["rarely_post", "finished_product", "process", "photo_video_mix"],
}


def test_four_map_covers_every_list_field() -> None:
    assert set(_FOUR) == set(LIST_FIELDS)
    assert MAX_CHOICES == 3


@pytest.mark.parametrize("field", sorted(_FOUR))
def test_four_items_rejected_three_accepted(field: str) -> None:
    with pytest.raises(ValidationError) as exc:
        SurveyAnswersV1.model_validate({field: _FOUR[field]})
    assert exc.value.errors()[0]["type"] == "too_long"
    ok = SurveyAnswersV1.model_validate({field: _FOUR[field][:3]})
    assert len(getattr(ok, field)) == 3


@pytest.mark.parametrize("field", sorted(_FOUR))
def test_unknown_code_rejected(field: str) -> None:
    with pytest.raises(ValidationError) as exc:
        SurveyAnswersV1.model_validate({field: ["not_a_real_code"]})
    assert exc.value.errors()[0]["type"] == "enum"


def test_duplicates_deduped_by_normalizer_order_preserved() -> None:
    answers = SurveyAnswersV1.model_validate({"q6_product_appeals": ["rarity", "design", "rarity"]})
    declared = normalize_survey(answers)
    assert declared.q6_product_appeals == [ProductAppeal.RARITY, ProductAppeal.DESIGN]


def test_q18_is_single_value_not_list() -> None:
    with pytest.raises(ValidationError):
        SurveyAnswersV1.model_validate({"q18_disclosure": ["yes"]})
    assert SurveyAnswersV1.model_validate({"q18_disclosure": "yes"}).q18_disclosure is (
        CreatorDisclosure.YES
    )
