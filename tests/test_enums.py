"""A. enum contract, B. UI option → stable code, C. Q10/Q11 namespace separation."""

from __future__ import annotations

import re
from enum import StrEnum

import pytest
from app.contracts.catalog import (
    CATALOG_ENUM_TYPES,
    MAX_SELECTIONS,
    UI_OPTION_CATALOG,
)
from app.contracts.diagnosis import SurveyAnswersV1
from app.contracts.enums import (
    BrandAttribute,
    CreatorDisclosure,
    CurrentReelFormat,
    DesiredEmotion,
    InstagramPainPoint,
    ProductAppeal,
    PurchaseMotive,
)

CONTRACT_V1_ENUMS: dict[type[StrEnum], list[str]] = {
    ProductAppeal: [
        "design",
        "color",
        "detail",
        "texture",
        "material",
        "process",
        "story",
        "rarity",
        "other",
    ],
    PurchaseMotive: [
        "aesthetic",
        "specialness",
        "self_reward",
        "gift",
        "memories",
        "space_decor",
        "self_expression",
    ],
    DesiredEmotion: [
        "excitement",
        "happiness",
        "warmth",
        "healing",
        "fun",
        "specialness",
        "moved",
        "comfort",
        "other",
    ],
    BrandAttribute: [
        "excitement",
        "happiness",
        "warmth",
        "healing",
        "fun",
        "specialness",
        "moved",
        "comfort",
        "other",
    ],
    InstagramPainPoint: [
        "low_reach",
        "low_follower_growth",
        "ideation",
        "shooting_difficulty",
        "editing_difficulty",
        "consistency_difficulty",
        "low_conversion",
        "other",
    ],
    CurrentReelFormat: [
        "rarely_post",
        "finished_product",
        "process",
        "photo_video_mix",
        "trend_reels",
        "vlog",
    ],
    CreatorDisclosure: ["yes", "no", "face_only", "voice_only"],
}

_SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


# ------------------------------------------------------------------ A. enum contract


@pytest.mark.parametrize(("enum_cls", "expected"), CONTRACT_V1_ENUMS.items())
def test_enum_values_match_contract_v1(enum_cls: type[StrEnum], expected: list[str]) -> None:
    actual = [m.value for m in enum_cls]
    assert set(actual) == set(expected)
    assert len(actual) == len(expected)
    assert len(set(expected)) == len(expected), "contract list itself must be unique"


@pytest.mark.parametrize("enum_cls", CONTRACT_V1_ENUMS.keys())
def test_enum_values_are_wire_strings(enum_cls: type[StrEnum]) -> None:
    for member in enum_cls:
        assert isinstance(member.value, str)
        assert _SNAKE.match(member.value), member
        assert enum_cls(member.value) is member


# ------------------------------------------------------------------ B. UI option → code


def test_catalog_covers_every_categorical_question() -> None:
    assert set(UI_OPTION_CATALOG) == {"q6", "q9", "q10", "q11", "q16", "q17", "q18"}
    assert set(CATALOG_ENUM_TYPES) == set(UI_OPTION_CATALOG)


@pytest.mark.parametrize("qid", sorted(UI_OPTION_CATALOG))
def test_every_label_maps_to_member_of_right_enum(qid: str) -> None:
    enum_cls = CATALOG_ENUM_TYPES[qid]
    for label, code in UI_OPTION_CATALOG[qid].items():
        assert label.strip() == label and label
        assert type(code) is enum_cls, (qid, label, code)
        assert _SNAKE.match(code.value)


@pytest.mark.parametrize("qid", sorted(UI_OPTION_CATALOG))
def test_every_member_appears_exactly_once_in_catalog(qid: str) -> None:
    enum_cls = CATALOG_ENUM_TYPES[qid]
    codes = list(UI_OPTION_CATALOG[qid].values())
    assert sorted(c.value for c in codes) == sorted(m.value for m in enum_cls)
    assert len(codes) == len(set(codes))


def test_specific_ssot_label_mappings() -> None:
    assert UI_OPTION_CATALOG["q6"]["제작 과정"] is ProductAppeal.PROCESS
    assert UI_OPTION_CATALOG["q9"]["나만의 것을 갖고 싶어서"] is PurchaseMotive.SELF_EXPRESSION
    assert UI_OPTION_CATALOG["q9"]["추억을 간직하려고"] is PurchaseMotive.MEMORIES
    assert UI_OPTION_CATALOG["q9"]["공간을 꾸미려고"] is PurchaseMotive.SPACE_DECOR
    assert UI_OPTION_CATALOG["q16"]["조회수가 안 나와요"] is InstagramPainPoint.LOW_REACH
    assert UI_OPTION_CATALOG["q17"]["거의 안 올려요"] is CurrentReelFormat.RARELY_POST
    assert UI_OPTION_CATALOG["q18"]["네"] is CreatorDisclosure.YES
    assert UI_OPTION_CATALOG["q18"]["아니요"] is CreatorDisclosure.NO


def test_max_selections_matches_contract() -> None:
    assert dict(MAX_SELECTIONS) == {"q6": 3, "q9": 3, "q10": 3, "q11": 3, "q16": 3, "q17": 3}
    assert "q18" not in MAX_SELECTIONS


# ------------------------------------------------------------------ C. Q10 / Q11 namespaces


def test_q10_and_q11_are_distinct_types_with_same_vocabulary() -> None:
    assert DesiredEmotion is not BrandAttribute
    assert not issubclass(DesiredEmotion, BrandAttribute)
    assert not issubclass(BrandAttribute, DesiredEmotion)
    assert {m.value for m in DesiredEmotion} == {m.value for m in BrandAttribute}
    assert DesiredEmotion.SPECIALNESS is not BrandAttribute.SPECIALNESS
    assert DesiredEmotion.SPECIALNESS == "specialness" == BrandAttribute.SPECIALNESS


def test_survey_answers_keep_q10_q11_typed_separately() -> None:
    answers = SurveyAnswersV1(
        q10_desired_emotions=["specialness"],
        q11_brand_attributes=["specialness"],
    )
    assert type(answers.q10_desired_emotions[0]) is DesiredEmotion
    assert type(answers.q11_brand_attributes[0]) is BrandAttribute
    assert type(answers.q10_desired_emotions[0]) is not type(answers.q11_brand_attributes[0])


def test_survey_schema_has_separate_defs_for_q10_and_q11() -> None:
    schema = SurveyAnswersV1.model_json_schema()
    defs = schema["$defs"]
    assert "DesiredEmotion" in defs and "BrandAttribute" in defs
    assert defs["DesiredEmotion"]["enum"] == defs["BrandAttribute"]["enum"]
    q10_ref = schema["properties"]["q10_desired_emotions"]["items"]["$ref"]
    q11_ref = schema["properties"]["q11_brand_attributes"]["items"]["$ref"]
    assert q10_ref.endswith("/DesiredEmotion")
    assert q11_ref.endswith("/BrandAttribute")
    assert q10_ref != q11_ref


def test_catalog_q10_and_q11_share_labels_but_not_members() -> None:
    q10, q11 = UI_OPTION_CATALOG["q10"], UI_OPTION_CATALOG["q11"]
    assert list(q10) == list(q11)
    for label in q10:
        assert q10[label] is not q11[label]
        assert q10[label].value == q11[label].value
