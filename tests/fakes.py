# ruff: noqa: E501
"""Scripted GeminiGateway fake + sample drafts for pipeline/validator/repair tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.domain.errors import SosuError
from app.domain.evidence import (
    InsightObservationV1,
    ScreenshotObservation,
    VisibleMetric,
    VisualObservationV1,
)
from app.gemini.gateway import GenerationSpec, ImagePart, StructuredResult, UsageRecord
from app.gemini.schemas import DiagnosisDraftV1, PrescriptionDraftV1
from app.images.types import NormalizedImage
from pydantic import BaseModel

Scripted = BaseModel | SosuError | Callable[..., BaseModel]


@dataclass(slots=True)
class RecordedCall:
    spec: GenerationSpec
    system_instruction: str
    user_text: str
    image_count: int
    schema: type[BaseModel]

    @property
    def text(self) -> str:
        return self.system_instruction + "\n" + self.user_text


@dataclass(slots=True)
class FakeGateway:
    """Returns scripted responses in order; records every call in `.calls`."""

    responses: list[Scripted] = field(default_factory=list)
    calls: list[RecordedCall] = field(default_factory=list)

    async def generate_structured(
        self,
        *,
        spec: GenerationSpec,
        system_instruction: str,
        user_text: str,
        images: list[ImagePart],
        schema: type[Any],
    ) -> StructuredResult[Any]:
        self.calls.append(
            RecordedCall(
                spec=spec,
                system_instruction=system_instruction,
                user_text=user_text,
                image_count=len(images),
                schema=schema,
            )
        )
        if not self.responses:
            raise AssertionError(f"FakeGateway: no scripted response for call #{len(self.calls)}")
        item = self.responses.pop(0)
        if isinstance(item, SosuError):
            raise item
        value = item(spec=spec, user_text=user_text) if callable(item) else item
        if not isinstance(value, schema):
            raise AssertionError(
                f"FakeGateway: scripted {type(value).__name__} but caller expected {schema.__name__}"
            )
        return StructuredResult(value=value, usage=UsageRecord(total_tokens=42), raw_json=None)


# ----------------------------------------------------------------------------- samples

BRAND = "모노유리"


def fake_image(n: int = 1) -> NormalizedImage:
    return NormalizedImage(data=b"\xff\xd8\xff" + bytes([n]) * 16, width=64, height=48)


def sample_visual() -> VisualObservationV1:
    return VisualObservationV1(
        visible_product_type="작은 유리 키링",
        dominant_visual_traits=["투명한 소재", "미세한 비즈 디테일"],
        material_cues=["유리로 보임"],
        strongest_visual_signal="빛 반사",
        possible_reel_assets=["빛 움직임", "매크로 디테일"],
        uncertainties=["크기는 판단 어려움"],
    )


def sample_insight() -> InsightObservationV1:
    return InsightObservationV1(
        screenshots=[
            ScreenshotObservation(
                source_index=i,
                visible_metrics=[VisibleMetric(label="조회수", value_text="1,204")],
                qualitative_notes=["막대 그래프 우상향"],
                unreadable_regions=[] if i else ["하단 잘림"],
            )
            for i in range(3)
        ],
        cross_image_signals=["세 장 모두 같은 기간 표기"],
    )


def diagnosis_draft_dict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "brand": {
            "name": BRAND,
            "material": "체코 유리비즈",
            "product": "유리 키링",
            "keywords": ["빛", "유리 디테일", "개별성"],
        },
        "positioning": {
            "summary": "빛에 따라 표정이 달라지는 작은 유리 오브제",
            "rationale": "사용자는 디자인과 희소성을 선언했고 이미지에서 반사가 관찰됩니다.",
        },
        "strengths": [
            {"title": "빛에 반응하는 소재감", "description": "움직임 속에서 반사가 드러납니다."},
            {
                "title": "개별 조합",
                "description": "같은 조합이 거의 없다는 점을 보여줄 수 있습니다.",
            },
        ],
        "target": {
            "summary": "개별성이 있는 소품을 찾는 20~30대",
            "description": "흔한 캐릭터 제품보다 독특한 소품을 선호합니다.",
        },
        "tone": {"keywords": ["따뜻한", "섬세한"], "description": "조용하고 반짝이는 분위기."},
        "fonts": {
            "title": "단정한 산세리프",
            "subtitle": "가독성 높은 산세리프",
            "reason": "값싸 보이는 인상을 피하기 위해.",
        },
        "priorities": [
            {"rank": 1, "title": "햇빛을 통과하는 유리", "description": "첫 3초에 반사 변화를."},
            {
                "rank": 2,
                "title": "손으로 연결하는 과정",
                "description": "비즈를 고르는 손 클로즈업.",
            },
            {"rank": 3, "title": "포장 전 확인 장면", "description": "햇빛에 비춰보는 장면."},
        ],
        "reel_types": [
            {"name": "제작 디테일형", "reason": "완성품 위주 콘텐츠의 gap을 보완합니다."},
            {"name": "빛 반사 무드형", "reason": "가장 강한 시각 자산을 활용합니다."},
            {"name": "자막 설명형", "reason": "목소리 없이 자막으로 차별점을 전달합니다."},
        ],
        "structure": {
            "hook_0_3": "햇빛에 제품을 움직여 색 변화 노출",
            "body_3_10": "비즈 고르는 손",
            "body_10_20": "하나씩 연결하는 과정",
            "close_20_27": "완성품을 창가에 두는 장면",
            "cta_27_30": "자막으로 프로필 링크 안내",
        },
        "final_guidance": ["움직임 속 반사를 우선 촬영하세요.", "자막으로 개별성을 설명하세요."],
    }
    base.update(overrides)
    return base


def sample_diagnosis_draft(**overrides: Any) -> DiagnosisDraftV1:
    return DiagnosisDraftV1.model_validate(diagnosis_draft_dict(**overrides))


def prescription_draft_dict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "prescription": {
            "summary": "도달은 있으나 저장/공유 전환이 약합니다.",
            "diagnosis": "조회수 1,204 대비 저장 수가 낮게 관찰됩니다.",
        },
        "next_actions": [
            {"order": 1, "title": "훅 재촬영", "description": "첫 3초에 빛 반사 장면 배치."},
            {"order": 2, "title": "자막 추가", "description": "차별점을 텍스트로 명시."},
            {"order": 3, "title": "업로드 시간 조정", "description": "저녁 8시대 테스트."},
            {"order": 4, "title": "CTA 명확화", "description": "저장 유도 문구 삽입."},
        ],
        "tone": {"keywords": ["따뜻한", "섬세한"], "description": "현재 톤 유지, 속도만 조절."},
    }
    base.update(overrides)
    return base


def sample_prescription_draft(**overrides: Any) -> PrescriptionDraftV1:
    return PrescriptionDraftV1.model_validate(prescription_draft_dict(**overrides))
