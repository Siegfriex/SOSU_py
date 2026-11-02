"""L — semantic validation: Q18 hard constraint, placeholders, rank/order integrity."""

from __future__ import annotations

from app.contracts.enums import CreatorDisclosure
from app.domain.evidence import CreatorConstraint
from app.domain.validator import (
    FACE_KEYWORDS,
    VOICE_KEYWORDS,
    ValidationOutcome,
    find_violations,
    is_placeholder,
    validate_diagnosis,
    validate_prescription,
)

from tests.fakes import (
    diagnosis_draft_dict,
    prescription_draft_dict,
    sample_diagnosis_draft,
    sample_prescription_draft,
)


def _c(d: CreatorDisclosure | None) -> CreatorConstraint:
    return CreatorConstraint.from_disclosure(d)


def _with_reel_reason(reason: str):
    d = diagnosis_draft_dict()
    d["reel_types"][0]["reason"] = reason
    return sample_diagnosis_draft(**d)


def test_clean_draft_passes_for_every_disclosure():
    for disc in (*CreatorDisclosure, None):
        report = validate_diagnosis(sample_diagnosis_draft(), _c(disc))
        assert report.outcome is ValidationOutcome.PASS, (disc, report.errors)


def test_face_only_plus_narration_is_caught():
    draft = _with_reel_reason("제작자가 내레이션으로 제작 과정을 설명하는 형식")
    report = validate_diagnosis(draft, _c(CreatorDisclosure.FACE_ONLY))
    assert report.outcome is ValidationOutcome.REPAIRABLE
    assert any("Q18" in e and "목소리" in e and "reel_types[0]" in e for e in report.errors)


def test_face_only_allows_face_but_not_voice_in_structure():
    d = diagnosis_draft_dict()
    d["structure"]["hook_0_3"] = "제작자의 얼굴이 웃으며 등장"
    assert validate_diagnosis(sample_diagnosis_draft(**d), _c(CreatorDisclosure.FACE_ONLY)).ok
    d["structure"]["body_3_10"] = "목소리로 소재를 설명"
    report = validate_diagnosis(sample_diagnosis_draft(**d), _c(CreatorDisclosure.FACE_ONLY))
    assert report.outcome is ValidationOutcome.REPAIRABLE
    assert any("structure.body_3_10" in e for e in report.errors)


def test_voice_only_plus_face_closeup_is_caught():
    d = diagnosis_draft_dict()
    d["priorities"][1]["description"] = "제작자의 얼굴을 클로즈업으로 보여주기"
    report = validate_diagnosis(sample_diagnosis_draft(**d), _c(CreatorDisclosure.VOICE_ONLY))
    assert report.outcome is ValidationOutcome.REPAIRABLE
    assert any("얼굴" in e and "priorities[1]" in e for e in report.errors)


def test_yes_allows_both():
    d = diagnosis_draft_dict()
    d["structure"]["hook_0_3"] = "제작자 얼굴 등장 후 내레이션 시작"
    assert validate_diagnosis(sample_diagnosis_draft(**d), _c(CreatorDisclosure.YES)).ok


def test_no_disclosure_with_neither_passes():
    assert validate_diagnosis(sample_diagnosis_draft(), _c(CreatorDisclosure.NO)).ok


def test_no_disclosure_catches_both_kinds():
    d = diagnosis_draft_dict()
    d["final_guidance"].append("얼굴과 목소리를 모두 활용하세요.")
    report = validate_diagnosis(sample_diagnosis_draft(**d), _c(CreatorDisclosure.NO))
    kinds = [e for e in report.errors if "final_guidance[2]" in e]
    assert len(kinds) == 2


def test_negation_is_compliant():
    draft = _with_reel_reason("내레이션 대신 자막으로 설명하는 형식")
    assert validate_diagnosis(draft, _c(CreatorDisclosure.FACE_ONLY)).ok
    d = diagnosis_draft_dict()
    d["structure"]["hook_0_3"] = "얼굴 노출 없이 손과 제품만"
    d["structure"]["body_3_10"] = "목소리를 쓰지 않고 BGM만"
    assert validate_diagnosis(sample_diagnosis_draft(**d), _c(CreatorDisclosure.NO)).ok


def test_ascii_keywords_need_word_boundaries():
    assert find_violations("smooth surface and clean interface", FACE_KEYWORDS) == []
    assert find_violations("talking head intro", FACE_KEYWORDS) == ["talking head"]
    assert find_violations("no narration, captions only", VOICE_KEYWORDS) == []
    assert find_violations("add a voice-over", VOICE_KEYWORDS) == ["voice-over"]


def test_placeholders_are_caught():
    for token in ("...", "…", "N/A", "TBD", "  ", "미정", "Lorem ipsum dolor"):
        assert is_placeholder(token), token
    assert not is_placeholder("빛에 반응하는 소재감")

    d = diagnosis_draft_dict()
    d["positioning"]["rationale"] = "..."
    report = validate_diagnosis(sample_diagnosis_draft(**d), _c(None))
    assert report.outcome is ValidationOutcome.REPAIRABLE
    assert any("positioning.rationale" in e for e in report.errors)


def test_duplicate_rank_is_caught():
    d = diagnosis_draft_dict()
    d["priorities"][2]["rank"] = 1
    report = validate_diagnosis(sample_diagnosis_draft(**d), _c(None))
    assert report.outcome is ValidationOutcome.REPAIRABLE
    assert any(e.startswith("priorities: rank") for e in report.errors)


def test_empty_keyword_lists_are_caught():
    d = diagnosis_draft_dict()
    d["tone"]["keywords"] = []
    report = validate_diagnosis(sample_diagnosis_draft(**d), _c(None))
    assert any(e.startswith("tone.keywords") for e in report.errors)


def test_all_placeholder_draft_is_fatal():
    d = diagnosis_draft_dict()
    for key in ("brand", "positioning", "target", "tone", "fonts", "structure"):
        for k, v in d[key].items():
            if isinstance(v, str):
                d[key][k] = "..."
    for item in d["strengths"] + d["priorities"] + d["reel_types"]:
        for k, v in item.items():
            if isinstance(v, str) and k != "code":
                item[k] = "N/A"
    d["final_guidance"] = ["..."]
    report = validate_diagnosis(sample_diagnosis_draft(**d), _c(None))
    assert report.outcome is ValidationOutcome.FATAL


def test_prescription_validation():
    assert validate_prescription(sample_prescription_draft()).ok
    d = prescription_draft_dict()
    d["next_actions"][3]["order"] = 2
    report = validate_prescription(sample_prescription_draft(**d))
    assert report.outcome is ValidationOutcome.REPAIRABLE
    assert any(e.startswith("next_actions: order") for e in report.errors)
    d = prescription_draft_dict()
    d["prescription"]["diagnosis"] = "TBD"
    assert not validate_prescription(sample_prescription_draft(**d)).ok


def test_strengths_are_checked_for_q18():
    d = diagnosis_draft_dict()
    d["strengths"][0]["description"] = "제작자가 카메라 앞에서 얼굴을 보여주며 목소리로 설명합니다."
    report = validate_diagnosis(sample_diagnosis_draft(**d), _c(CreatorDisclosure.NO))
    assert report.outcome is ValidationOutcome.REPAIRABLE
    assert any("strengths[0]" in e for e in report.errors)


def test_compliant_framing_is_not_a_violation():
    for text in (
        "얼굴이 나오지 않게 손만 클로즈업",
        "얼굴은 가리고 손 위주로",
        "얼굴이 보이지 않도록 목 아래만",
    ):
        assert find_violations(text, FACE_KEYWORDS) == [], text


def test_spoken_guidance_phrases_are_voice():
    for text in ("자막과 안내 멘트를 배치", "인터뷰 형식으로 말로 설명"):
        assert find_violations(text, VOICE_KEYWORDS), text


def test_prescription_causal_claim_is_caught():
    d = prescription_draft_dict()
    d["prescription"]["diagnosis"] = "높은 시청 지속 덕분에 조회수가 크게 늘었습니다."
    report = validate_prescription(sample_prescription_draft(**d))
    assert report.outcome is ValidationOutcome.REPAIRABLE
    assert any("덕분에" in e for e in report.errors)
