"""N — orchestration with a mocked gateway: call order, isolation, image routing."""

from __future__ import annotations

import pytest
from app.config import Settings
from app.contracts.diagnosis import SurveyDiagnosisRequestV1
from app.contracts.envelope import ErrorCode
from app.contracts.prescription import PrescriptionRequestV1
from app.domain.errors import SosuError
from app.domain.evidence import InsightObservationV1, VisualObservationV1
from app.gemini.schemas import DiagnosisDraftV1, PrescriptionDraftV1
from app.services.diagnosis_service import DiagnosisService
from app.services.prescription_service import PrescriptionService

from tests.fakes import (
    BRAND,
    FakeGateway,
    diagnosis_draft_dict,
    fake_image,
    sample_diagnosis_draft,
    sample_insight,
    sample_prescription_draft,
    sample_visual,
)

SETTINGS = Settings(
    gemini_api_key="test-key-not-real",  # type: ignore[arg-type]
    gemini_model_observe="observe-model",
    gemini_model_diagnosis="diagnosis-model",
    gemini_model_prescription="prescription-model",
)

DISTINCT_TEXT = "다른 데는 보통 파스텔 조합만 하는데 저는 일부러 투명한 거랑 탁한 색을 섞어요"


def _request() -> SurveyDiagnosisRequestV1:
    return SurveyDiagnosisRequestV1.model_validate(
        {
            "contract_version": "1.0",
            "locale": "ko-KR",
            "answers": {
                "q1_brand_name": BRAND,
                "q3_hero_product": "빛에 따라 색이 달라 보이는 유리 키링",
                "q6_product_appeals": ["design", "rarity"],
                "q7_differentiation": DISTINCT_TEXT,
                "q10_desired_emotions": ["specialness"],
                "q11_brand_attributes": ["warmth"],
                "q18_disclosure": "face_only",
            },
        }
    )


async def test_diagnosis_with_image_makes_two_calls_and_isolates_observation():
    gw = FakeGateway([sample_visual(), sample_diagnosis_draft()])
    report = await DiagnosisService(gw, settings=SETTINGS).run(
        _request(), fake_image(), request_id="r1"
    )

    assert len(gw.calls) == 2
    observe, synth = gw.calls

    assert observe.schema is VisualObservationV1
    assert observe.image_count == 1
    assert observe.spec.model == "observe-model"
    assert observe.spec.thinking == "low"
    assert observe.spec.max_output_tokens == 2048
    assert observe.spec.prompt_version == "visual-observation-v1"
    for forbidden in (BRAND, DISTINCT_TEXT, "유리 키링", "face_only", "rarity"):
        assert forbidden not in observe.text

    assert synth.schema is DiagnosisDraftV1
    assert synth.image_count == 0
    assert synth.spec.model == "diagnosis-model"
    assert synth.spec.thinking == "medium"
    assert synth.spec.max_output_tokens == 8192
    assert synth.spec.prompt_version == "diagnosis-v1"
    assert BRAND in synth.user_text
    assert DISTINCT_TEXT in synth.user_text  # verbatim, never summarized
    assert "빛 반사" in synth.user_text  # visual observation was injected
    assert "목소리 사용 불가" in synth.user_text  # derived constraint rendered

    assert report.schema_version == "diagnosis.v1"
    assert [p.rank for p in report.priorities] == [1, 2, 3]


async def test_diagnosis_without_image_skips_observation():
    gw = FakeGateway([sample_diagnosis_draft()])
    report = await DiagnosisService(gw, settings=SETTINGS).run(_request(), None, request_id="r2")
    assert len(gw.calls) == 1
    assert gw.calls[0].schema is DiagnosisDraftV1
    assert "이미지 없음" in gw.calls[0].user_text
    assert report.brand.name == BRAND


async def test_diagnosis_repair_path_uses_repair_spec():
    bad = diagnosis_draft_dict()
    bad["structure"]["body_3_10"] = "제작자가 목소리로 소재를 설명"
    gw = FakeGateway([sample_diagnosis_draft(**bad), sample_diagnosis_draft()])
    await DiagnosisService(gw, settings=SETTINGS).run(_request(), None, request_id="r3")
    assert [c.spec.prompt_version for c in gw.calls] == ["diagnosis-v1", "repair-v1"]
    repair = gw.calls[1].spec
    assert repair.model == "diagnosis-model"
    assert repair.thinking == "low"
    assert repair.max_output_tokens == 4096


async def test_gateway_error_propagates_unchanged():
    err = SosuError(ErrorCode.MODEL_PROVIDER_ERROR, "boom", details=[{"status": 503}])
    gw = FakeGateway([err])
    with pytest.raises(SosuError) as exc:
        await DiagnosisService(gw, settings=SETTINGS).run(_request(), fake_image(), request_id="r4")
    assert exc.value is err
    assert len(gw.calls) == 1


async def test_prescription_pipeline():
    gw = FakeGateway([sample_insight(), sample_prescription_draft()])
    req = PrescriptionRequestV1(instagram_url="https://www.instagram.com/reel/Cabc123_-/")
    report = await PrescriptionService(gw, settings=SETTINGS).run(
        req, [fake_image(1), fake_image(2), fake_image(3)], request_id="p1"
    )
    assert len(gw.calls) == 2
    observe, synth = gw.calls
    assert observe.schema is InsightObservationV1
    assert observe.image_count == 3
    assert observe.spec.model == "observe-model"
    assert observe.spec.prompt_version == "insight-observation-v1"
    assert synth.schema is PrescriptionDraftV1
    assert synth.image_count == 0
    assert synth.spec.model == "prescription-model"
    assert synth.spec.max_output_tokens == 4096
    assert synth.spec.prompt_version == "prescription-v1"
    assert req.instagram_url in synth.user_text
    assert "미관측" in synth.user_text
    assert "하단 잘림" in synth.user_text  # unreadable regions are forwarded, not filled
    assert report.schema_version == "prescription.v1"
    assert [a.order for a in report.next_actions] == [1, 2, 3, 4]
