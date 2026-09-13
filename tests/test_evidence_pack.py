"""InferencePolicyV1 routing and EvidencePackV1 assembly."""

from __future__ import annotations

from typing import Any, get_args

from app.contracts.diagnosis import SurveyAnswersV1
from app.domain.evidence import EvidencePackV1, ReportSection, VisualObservationV1
from app.domain.evidence_pack import build_evidence_pack, evidence_meta
from app.domain.normalizer import normalize_survey
from app.domain.policy import INFERENCE_POLICY_V1, VISUAL

ALL_SECTIONS = set(get_args(ReportSection))
Q18_CONSTRAINED: tuple[ReportSection, ...] = (
    "priorities",
    "reel_types",
    "structure",
    "final_guidance",
)


def test_policy_has_all_nine_sections() -> None:
    assert set(INFERENCE_POLICY_V1.routing) == ALL_SECTIONS
    assert len(ALL_SECTIONS) == 9
    assert INFERENCE_POLICY_V1.version == "inference-policy-v1"


def test_every_section_has_non_empty_primary() -> None:
    for section, routing in INFERENCE_POLICY_V1.routing.items():
        assert routing.primary, section


def test_q18_constraint_sections() -> None:
    for section in Q18_CONSTRAINED:
        assert "q18" in INFERENCE_POLICY_V1.routing[section].constraint, section
    assert INFERENCE_POLICY_V1.routing["positioning"].constraint == ["q12"]


def test_policy_matches_contract_section_12() -> None:
    r = INFERENCE_POLICY_V1.routing
    assert r["positioning"].primary == ["q2", "q3", "q5", "q6", "q7"]
    assert r["positioning"].supporting == ["q8", "q9", "q11", "q13", VISUAL]
    assert r["strengths"].primary == ["q3", "q4", "q5", "q6", "q7", VISUAL]
    assert r["target"].primary == ["q8", "q9", "q10"]
    assert r["tone"].primary == ["q10", "q11", "q12", "q13"]
    assert r["fonts"].primary == ["q11", "q12", "q13"]
    assert r["priorities"].primary == ["q14", "q15", "q20", VISUAL]
    assert r["reel_types"].primary == ["q16", "q17", "q15"]
    assert r["structure"].primary == ["q14", "q15", "q17", "q20", VISUAL]
    assert r["final_guidance"].primary == ["q16", "q17", "q18"]


def test_policy_has_no_numeric_weights() -> None:
    dumped = INFERENCE_POLICY_V1.model_dump()
    for routing in dumped["routing"].values():
        for role in ("primary", "supporting", "constraint"):
            assert all(isinstance(x, str) for x in routing[role])


def test_build_pack_without_visual(sample_answers: dict[str, Any]) -> None:
    declared = normalize_survey(SurveyAnswersV1.model_validate(sample_answers))
    pack = build_evidence_pack(declared, None)
    assert isinstance(pack, EvidencePackV1)
    assert pack.visual is None
    assert pack.policy is INFERENCE_POLICY_V1
    assert pack.locale == "ko-KR"
    assert pack.declared is declared


def test_build_pack_with_visual(sample_answers: dict[str, Any]) -> None:
    declared = normalize_survey(SurveyAnswersV1.model_validate(sample_answers))
    visual = VisualObservationV1(
        visible_product_type="small_accessory",
        dominant_visual_traits=["transparent material"],
        strongest_visual_signal="light reflection",
    )
    pack = build_evidence_pack(declared, visual, locale="en-US")
    assert pack.visual is visual
    assert pack.locale == "en-US"


def test_evidence_meta_counts_full_sample(sample_answers: dict[str, Any]) -> None:
    declared = normalize_survey(SurveyAnswersV1.model_validate(sample_answers))
    meta = evidence_meta(build_evidence_pack(declared, VisualObservationV1()))
    assert meta == {
        "has_product_image": True,
        "answered_fields": 19,
        "categorical_fields": 7,  # q6 q9 q10 q11 q16 q17 q18
        "free_text_fields": 12,  # q1-5, q7, q8, q12-15, q20
    }


def test_evidence_meta_counts_partial() -> None:
    declared = normalize_survey(
        SurveyAnswersV1.model_validate(
            {"q3_hero_product": "유리 키링", "q6_product_appeals": ["design"]}
        )
    )
    meta = evidence_meta(build_evidence_pack(declared, None))
    assert meta == {
        "has_product_image": False,
        "answered_fields": 2,
        "categorical_fields": 1,
        "free_text_fields": 1,
    }
