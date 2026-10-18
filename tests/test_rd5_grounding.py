# ruff: noqa: E501
"""RD-5 — prescription grounding: no video content inferred from handle/URL or unseen frames.

Deterministic: direct validator calls + FakeGateway pipeline runs. No live Gemini.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.config import Settings
from app.contracts.envelope import ErrorCode
from app.contracts.prescription import PrescriptionRequestV1
from app.domain.errors import SosuError
from app.domain.evidence import InsightObservationV1, ScreenshotObservation, VisibleMetric
from app.domain.validator import (
    ValidationOutcome,
    ValidationReport,
    build_grounding_evidence,
    validate_prescription,
)
from app.gemini.prompts import insight_observation as insight_prompt
from app.gemini.prompts import prescription as prescription_prompt
from app.gemini.schemas import PrescriptionDraftV1
from app.services.prescription_service import PrescriptionService

from tests.fakes import FakeGateway, fake_image

SETTINGS = Settings(
    gemini_api_key="test-key-not-real",  # type: ignore[arg-type]
    gemini_model_observe="observe-model",
    gemini_model_diagnosis="diagnosis-model",
    gemini_model_prescription="prescription-model",
)

HANDLE = "@sosu_smoke_ceramics"
SMOKE_URL = "https://www.instagram.com/reel/SOSUsmoke01/"
NEUTRAL_URL = "https://www.instagram.com/reel/Cabc123_-/"


# ----------------------------------------------------------------------------- fixtures


def live_like_observation(
    *,
    handle: str = HANDLE,
    extra_notes: list[str] | None = None,
    unreadable: list[str] | None = None,
    drop_labels: tuple[str, ...] = (),
) -> InsightObservationV1:
    """Replica of the 2026-10-18 live insight observation (metrics + handle in notes)."""
    shots: list[list[tuple[str, str]]] = [
        [
            ("조회수", "12,480"),
            ("도달한 계정", "9,830"),
            ("팔로워 아닌 계정 비율", "78%"),
            ("좋아요", "412"),
            ("댓글", "18"),
            ("공유", "37"),
            ("저장", "96"),
        ],
        [
            ("평균 시청 시간", "6.2초"),
            ("영상 길이", "15초"),
            ("3초 이탈률", "41%"),
            ("다시 본 비율", "12%"),
            ("총 시청 시간", "21시간 29분"),
        ],
        [
            ("프로필 방문", "214"),
            ("팔로우", "23"),
            ("유입: 탐색 탭", "52%"),
            ("유입: 릴스 탭", "31%"),
        ],
    ]
    screenshots = []
    for i, metrics in enumerate(shots):
        notes = ["상단 제목 '< 릴스 인사이트'"]
        if handle:
            notes.append(f"화면 텍스트(영상 내용 아님): '{handle} · 2026년 10월 3일 게시'")
        if i == 0 and extra_notes:
            notes.extend(extra_notes)
        screenshots.append(
            ScreenshotObservation(
                source_index=i,
                visible_metrics=[
                    VisibleMetric(label=label, value_text=value)
                    for label, value in metrics
                    if label not in drop_labels
                ],
                qualitative_notes=notes,
                unreadable_regions=(unreadable or []) if i == 0 else [],
            )
        )
    signals = ["세 장 모두 섹션 제목이 다름"]
    if handle:
        signals.append(f"모든 스크린샷 상단에 동일한 계정명({handle})이 표기됨")
    return InsightObservationV1(screenshots=screenshots, cross_image_signals=signals)


def clean_draft_dict(**overrides: Any) -> dict[str, Any]:
    """Grounded draft: metrics only + guidebook techniques + explicitly hypothetical ideas."""
    base: dict[str, Any] = {
        "prescription": {
            "summary": "팔로워 아닌 계정 비율 78%와 유입: 탐색 탭 52%로 신규 도달은 높지만, 3초 이탈률 41%로 초반 유지가 약했을 가능성이 있습니다.",
            "diagnosis": "확인된 지표 기준으로 조회수 12,480회, 도달한 계정 9,830개입니다. 평균 시청 시간 6.2초는 영상 길이 15초의 약 41%로, 끝까지 보기 전에 이탈한 시청자가 많았을 가능성이 있습니다. 프로필 방문 214회 대비 팔로우 23명입니다.",
        },
        "next_actions": [
            {
                "order": 1,
                "title": "첫 3초에 완성작과 궁금증형 카피 배치",
                "description": "3초 이탈률(41%)을 줄이기 위해 다음 영상에서는 첫 2~3초 안에 완성작을 먼저 보여주고 궁금증을 만드는 한 줄 카피를 올려 보세요.",
            },
            {
                "order": 2,
                "title": "2~3초 단위 컷 편집",
                "description": "평균 시청 시간(6.2초)을 늘리기 위해 한 구도가 5초를 넘지 않도록 2~3초 단위로 자르고, 45° 측광과 매크로 클로즈업으로 질감을 보여주세요.",
            },
            {
                "order": 3,
                "title": "캡션 끝 참여형 질문",
                "description": "댓글 18개와 저장 96개를 늘리기 위해 다음 영상에서 시도해 볼 수 있는 예: 캡션 마지막 줄에 '이 작품, 어디에 두고 싶으세요?' 같은 질문을 남겨 보세요.",
            },
            {
                "order": 4,
                "title": "프로필 첫 줄 정돈",
                "description": "프로필 방문 214회가 팔로우 23명으로 더 이어지도록 프로필 첫 줄에 브랜드 한 줄 소개를 적어 두세요.",
            },
        ],
        "tone": {
            "keywords": ["담백한", "리듬감 있는", "친근한"],
            "description": "작업 과정의 시각적 변화를 담백하게 전달하고 친근한 어조를 유지해 보세요.",
        },
    }
    base.update(overrides)
    return base


def draft(**overrides: Any) -> PrescriptionDraftV1:
    return PrescriptionDraftV1.model_validate(clean_draft_dict(**overrides))


def with_action(index: int, description: str) -> PrescriptionDraftV1:
    d = clean_draft_dict()
    d["next_actions"][index]["description"] = description
    return PrescriptionDraftV1.model_validate(d)


def with_diagnosis(text: str) -> PrescriptionDraftV1:
    d = clean_draft_dict()
    d["prescription"]["diagnosis"] = text
    return PrescriptionDraftV1.model_validate(d)


def check(
    d: PrescriptionDraftV1,
    obs: InsightObservationV1 | None = None,
    url: str = NEUTRAL_URL,
) -> ValidationReport:
    return validate_prescription(
        d, observation=obs if obs is not None else live_like_observation(), instagram_url=url
    )


def assert_grounding_flag(report: ValidationReport, needle: str) -> None:
    assert report.outcome is ValidationOutcome.REPAIRABLE, report.errors
    assert any(needle in e for e in report.errors), report.errors


# ----------------------------------------------------------------------------- baseline


def test_clean_grounded_draft_passes():
    report = check(draft())
    assert report.ok, report.errors


def test_legacy_signature_still_structural_only():
    # Old one-argument call keeps working (no evidence → no grounding checks).
    assert validate_prescription(draft()).ok


def test_evidence_strips_handle_from_observed_text():
    ev = build_grounding_evidence(live_like_observation(), SMOKE_URL)
    assert "ceramics" not in ev.observed_text
    assert ev.handle_sources["ceramic"] == HANDLE
    assert ev.handle_sources["smoke"] in {HANDLE, "SOSUsmoke01"}


# ----------------------------------------------------------------------------- adversarial


def test_handle_product_asserted_as_video_content_is_flagged():
    report = check(
        with_diagnosis("이 영상에서 도자기에 연기를 입히는 과정을 보여준 점이 좋았습니다.")
    )
    assert_grounding_flag(report, "'도자기'")
    assert_grounding_flag(report, "@sosu_smoke_ceramics")
    assert all("placeholder" not in e for e in report.errors)  # never escalates to FATAL


def test_handle_process_name_is_flagged():
    obs = live_like_observation(handle="@hana_candle_pour")
    report = check(
        with_action(0, "첫 장면에 캔들 왁스를 붓는 장면을 넣어 3초 이탈률(41%)을 줄여 보세요."),
        obs,
    )
    assert_grounding_flag(report, "'캔들'")


def test_handle_derived_noun_flagged_even_when_phrased_as_example():
    report = check(
        with_action(0, "화면 상단에 '도자기를 굽는 비밀'과 같은 궁금증형 카피를 올려 보세요.")
    )
    assert_grounding_flag(report, "'도자기'")


def test_url_slug_suggestive_is_flagged():
    obs = live_like_observation(handle="")
    report = check(
        with_action(1, "연기가 피어오르는 순간을 2~3초 컷으로 이어 붙여 보세요."), obs, SMOKE_URL
    )
    assert_grounding_flag(report, "SOSUsmoke01")
    assert_grounding_flag(report, "'연기'")


def test_unseen_frame_asserted_about_analysed_reel_is_flagged():
    report = check(with_diagnosis("영상 속 머그를 돌리는 장면이 너무 길었습니다."), url=NEUTRAL_URL)
    assert_grounding_flag(report, "근거 없는 영상 내용 단정")


def test_watch_claim_is_flagged():
    report = check(with_diagnosis("영상을 확인해 보니 초반 3초가 정적이었습니다."))
    assert_grounding_flag(report, "영상 시청 주장")


def test_only_aggregate_metrics_generic_next_video_ideas_pass():
    obs = live_like_observation(handle="")
    d = with_action(
        0,
        "다음 영상에서는 예를 들어 완성작을 먼저 보여주고 작업 과정을 2~3초 컷으로 이어 붙여 보세요.",
    )
    report = validate_prescription(d, observation=obs, instagram_url=NEUTRAL_URL)
    assert report.ok, report.errors


def test_hedged_metric_reading_about_this_reel_passes():
    report = check(
        with_diagnosis(
            "이 영상의 3초 이탈률 41%를 보면 초반 장면이 시선을 붙잡기에 약했을 가능성이 있습니다."
        )
    )
    assert report.ok, report.errors


def test_product_visible_in_screenshot_text_may_be_cited_as_screenshot_text():
    obs = live_like_observation(
        extra_notes=["화면 텍스트(영상 내용 아님): '도자기 머그 원데이 클래스 오픈'"]
    )
    d = with_diagnosis(
        "스크린샷에 보이는 '도자기 머그 원데이 클래스 오픈' 문구 기준으로, 조회수 12,480회 중 저장 96개입니다."
    )
    report = check(d, obs)
    assert report.ok, report.errors


def test_unreadable_metric_with_number_is_flagged():
    obs = live_like_observation(
        unreadable=["공유 수 영역이 잘려 읽을 수 없음"], drop_labels=("공유",)
    )
    flagged = check(with_diagnosis("공유 37회로 확산이 약했습니다."), obs)
    assert_grounding_flag(flagged, "읽을 수 없는 지표 '공유'")
    ok = check(
        with_diagnosis(
            "공유 수는 화면이 잘려 읽을 수 없어 판단에서 제외했습니다. 저장 96개입니다."
        ),
        obs,
    )
    assert ok.ok, ok.errors


def test_derived_completion_calc_is_allowed():
    report = check(
        with_diagnosis(
            "평균 시청 시간 6.2초 ÷ 영상 길이 15초로 계산하면 시청 완료 비율은 약 41%이며, 총 시청 시간은 21시간 29분입니다."
        )
    )
    assert report.ok, report.errors


def test_guidebook_filming_technique_next_action_is_allowed():
    report = check(
        with_action(
            1,
            "가이드북 권장대로 45° 측광과 매크로 클로즈업, 2~3초 컷 전환으로 손동작과 질감을 보여주세요.",
        )
    )
    assert report.ok, report.errors


# ----------------------------------------------------------------------------- live replica

# Offending sentences copied verbatim from .sprint/live_smoke_result.json (2026-10-18 14:08 KST run).
LIVE_OFFENDING_ACTION_1 = "초반 3초 이탈률(41%)을 줄이기 위해 첫 장면에 도자기 완성품을 2~3초 이내로 먼저 보여주고, 화면 상단에 '도자기에 연기를 입히는 비밀 과정'과 같은 궁금증형 카피를 함께 올려 시청을 붙잡아 보세요."
LIVE_OFFENDING_ACTION_2 = "평균 시청 시간(6.2초)을 늘리기 위해 한 구도가 5초를 넘기지 않도록 2~3초 단위로 자르고, 흙 반죽부터 다듬기까지 핵심 손동작 위주로 리듬감 있게 이어 붙여 보세요."
LIVE_OFFENDING_ACTION_3 = "댓글 18개와 저장 96개의 반응을 더 끌어올리기 위해 캡션 끝에 '작업실에서 방금 나온 화병, 거실과 침실 중 어디에 더 어울릴까요?'처럼 시청자가 바로 고를 수 있는 질문 하나를 남겨 보세요."
LIVE_OFFENDING_TONE = "장황한 설명 대신 도자기 제작 과정의 시각적 변화와 현장 소리를 담백하게 전달하고, 시청자가 부담 없이 댓글로 대화에 참여할 수 있도록 친근하고 명확한 어조를 유지해 보세요."


def live_hallucinating_draft() -> PrescriptionDraftV1:
    d = clean_draft_dict()
    d["next_actions"][0]["description"] = LIVE_OFFENDING_ACTION_1
    d["next_actions"][1]["description"] = LIVE_OFFENDING_ACTION_2
    d["next_actions"][2]["description"] = LIVE_OFFENDING_ACTION_3
    d["tone"]["description"] = LIVE_OFFENDING_TONE
    return PrescriptionDraftV1.model_validate(d)


def test_live_2026_10_18_output_is_flagged():
    report = check(live_hallucinating_draft(), url=SMOKE_URL)
    assert report.outcome is ValidationOutcome.REPAIRABLE
    joined = "\n".join(report.errors)
    for path in ("next_actions[0]", "next_actions[1]", "next_actions[2]", "tone.description"):
        assert path in joined, joined
    for noun in ("'도자기'", "'연기'", "'흙'", "'화병'"):
        assert noun in joined, joined


@pytest.mark.parametrize(
    "sentence", [LIVE_OFFENDING_ACTION_1, LIVE_OFFENDING_ACTION_2, LIVE_OFFENDING_ACTION_3]
)
def test_each_live_sentence_alone_is_flagged(sentence: str):
    assert check(with_action(3, sentence)).outcome is ValidationOutcome.REPAIRABLE


# ----------------------------------------------------------------------------- prompts


def test_prescription_prompt_has_evidence_boundary_and_redacts_handle():
    system, user = prescription_prompt.build_prescription_prompt(
        live_like_observation(), instagram_url=SMOKE_URL
    )
    assert "EVIDENCE BOUNDARY" in system
    assert "다음 영상에서 시도해 볼 수 있는 예" in system
    assert "계정명(@…)이나 URL 경로" in system
    assert "시청한 것처럼" in system
    assert "인과로 단정" in system
    assert "스크린샷에 보이는 '…' 문구" in system
    # Raw handle never reaches the synthesis model; only the redaction marker does.
    assert HANDLE not in user and "ceramics" not in user
    assert prescription_prompt.HANDLE_REDACTION in user
    # The metrics themselves are still forwarded verbatim.
    assert "12,480" in user and "6.2초" in user
    # No content noun primed by the prompt itself.
    assert "도자기" not in system + user


def test_observation_prompt_labels_screen_text_not_video_content():
    system, user = insight_prompt.build_insight_observation_prompt()
    assert "화면 텍스트(영상 내용 아님)" in system
    assert "영상 장면·제품·소재·제작 과정" in system
    assert "화면 텍스트(영상 내용 아님)" in user


# ----------------------------------------------------------------------------- pipeline


def _request() -> PrescriptionRequestV1:
    return PrescriptionRequestV1(instagram_url=SMOKE_URL)


def _images():
    return [fake_image(1), fake_image(2), fake_image(3)]


async def test_pipeline_hallucinating_draft_then_clean_repair_returns_clean():
    gw = FakeGateway([live_like_observation(), live_hallucinating_draft(), draft()])
    report = await PrescriptionService(gw, settings=SETTINGS).run(
        _request(), _images(), request_id="rd5-1"
    )
    assert [c.spec.prompt_version for c in gw.calls] == [
        insight_prompt.PROMPT_VERSION,
        prescription_prompt.PROMPT_VERSION,
        "repair-v1",
    ]
    repair_text = gw.calls[2].user_text
    assert "근거 없는 영상 내용" in repair_text
    assert "'도자기'" in repair_text
    assert "계정명(@handle)·URL은 식별자일 뿐" in repair_text
    assert report.next_actions[0].description == draft().next_actions[0].description
    assert "도자기" not in report.model_dump_json()


async def test_pipeline_hallucinating_repair_too_raises_repair_failed():
    gw = FakeGateway(
        [live_like_observation(), live_hallucinating_draft(), live_hallucinating_draft()]
    )
    with pytest.raises(SosuError) as exc:
        await PrescriptionService(gw, settings=SETTINGS).run(
            _request(), _images(), request_id="rd5-2"
        )
    assert exc.value.code is ErrorCode.REPAIR_FAILED
    assert len(gw.calls) == 3


async def test_pipeline_clean_draft_needs_no_repair():
    gw = FakeGateway([live_like_observation(), draft()])
    await PrescriptionService(gw, settings=SETTINGS).run(_request(), _images(), request_id="rd5-3")
    assert len(gw.calls) == 2


# ----------------------------------------------------------------------------- false-positive guards


@pytest.mark.parametrize(
    "sentence",
    [
        "자막이 영상의 흐름을 끊지 않도록 2~3초 컷으로 넣어 보세요.",
        "다음 영상 속 첫 장면에 완성작을 먼저 배치해 3초 이탈률(41%)을 낮춰 보세요.",
        "직접 만드신 작품의 완성 장면을 첫 3초에 보여주세요.",
        "시청자가 영상을 보면 바로 결과를 알 수 있도록 완성작을 먼저 보여주세요.",
    ],
)
def test_natural_next_video_advice_is_not_flagged(sentence: str):
    report = check(with_action(1, sentence))
    assert report.ok, report.errors


def test_unreadable_prefix_label_does_not_flag_readable_longer_label():
    obs = live_like_observation(unreadable=["도달 출처 그래프 일부 잘림", "시청 시간 그래프 가림"])
    report = check(
        with_diagnosis(
            "도달한 계정 9,830개, 평균 시청 시간 6.2초, 총 시청 시간 21시간 29분입니다."
        ),
        obs,
    )
    assert report.ok, report.errors
