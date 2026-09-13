"""Internal evidence models. Not part of the public contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.enums import (
    BrandAttribute,
    CreatorDisclosure,
    CurrentReelFormat,
    DesiredEmotion,
    InstagramPainPoint,
    ProductAppeal,
    PurchaseMotive,
)


class CreatorConstraint(BaseModel):
    """HARD constraint derived from Q18. A recommendation violating it fails semantic validation."""

    face_allowed: bool
    voice_allowed: bool
    source: CreatorDisclosure | None = None

    @classmethod
    def from_disclosure(cls, disclosure: CreatorDisclosure | None) -> CreatorConstraint:
        if disclosure is None:
            # Unknown → treat as unconstrained (no hard evidence either way).
            return cls(face_allowed=True, voice_allowed=True, source=None)
        table: dict[CreatorDisclosure, tuple[bool, bool]] = {
            CreatorDisclosure.YES: (True, True),
            CreatorDisclosure.NO: (False, False),
            CreatorDisclosure.FACE_ONLY: (True, False),
            CreatorDisclosure.VOICE_ONLY: (False, True),
        }
        face, voice = table[disclosure]
        return cls(face_allowed=face, voice_allowed=voice, source=disclosure)


class DeclaredEvidenceV1(BaseModel):
    """Deterministically normalized survey answers. Text is never semantically rewritten."""

    model_config = ConfigDict(extra="forbid")

    q1_brand_name: str | None = None
    q2_product_category: str | None = None
    q3_hero_product: str | None = None
    q4_materials: str | None = None
    q5_material_reason: str | None = None
    q6_product_appeals: list[ProductAppeal] = Field(default_factory=list)
    q7_differentiation: str | None = None
    q8_target_customer: str | None = None
    q9_purchase_motives: list[PurchaseMotive] = Field(default_factory=list)
    q10_desired_emotions: list[DesiredEmotion] = Field(default_factory=list)
    q11_brand_attributes: list[BrandAttribute] = Field(default_factory=list)
    q12_avoidance: str | None = None
    q13_motif: str | None = None
    q14_primary_message: str | None = None
    q15_interesting_process: str | None = None
    q16_pain_points: list[InstagramPainPoint] = Field(default_factory=list)
    q17_current_formats: list[CurrentReelFormat] = Field(default_factory=list)
    q18_disclosure: CreatorDisclosure | None = None
    q20_must_show: str | None = None

    creator_constraint: CreatorConstraint
    answered_question_ids: list[str] = Field(default_factory=list)

    @property
    def has_meaningful_answer(self) -> bool:
        return bool(self.answered_question_ids)


class VisualObservationV1(BaseModel):
    """Independent image observation. The observation call never sees survey answers."""

    visible_product_type: str | None = Field(
        default=None, description="눈에 보이는 제품 유형. 확실하지 않으면 null."
    )
    dominant_visual_traits: list[str] = Field(
        default_factory=list, description="관찰 가능한 시각적 특징(색, 형태, 질감 등)."
    )
    material_cues: list[str] = Field(
        default_factory=list, description="소재로 보이는 단서. 추정이면 '~로 보임'을 명시."
    )
    strongest_visual_signal: str | None = Field(
        default=None, description="가장 눈에 띄는 단일 시각 신호."
    )
    possible_reel_assets: list[str] = Field(
        default_factory=list, description="릴스 소재로 쓸 수 있는 관찰 가능한 요소."
    )
    uncertainties: list[str] = Field(
        default_factory=list, description="확실하지 않은 점. 사실과 추론을 구분."
    )


class VisibleMetric(BaseModel):
    label: str = Field(description="화면에 보이는 지표 라벨 그대로.")
    value_text: str = Field(description="화면에 보이는 값 텍스트 그대로(숫자 변환 금지).")


class ScreenshotObservation(BaseModel):
    source_index: int = Field(description="스크린샷 순번(0 기반).")
    visible_metrics: list[VisibleMetric] = Field(default_factory=list)
    qualitative_notes: list[str] = Field(default_factory=list)
    unreadable_regions: list[str] = Field(
        default_factory=list, description="읽을 수 없는 영역. 절대 값을 추정하지 않음."
    )


class InsightObservationV1(BaseModel):
    screenshots: list[ScreenshotObservation] = Field(default_factory=list)
    cross_image_signals: list[str] = Field(default_factory=list)


EvidenceRole = Literal["primary", "supporting", "constraint"]
ReportSection = Literal[
    "positioning",
    "strengths",
    "target",
    "tone",
    "fonts",
    "priorities",
    "reel_types",
    "structure",
    "final_guidance",
]


class SectionRouting(BaseModel):
    primary: list[str]
    supporting: list[str] = Field(default_factory=list)
    constraint: list[str] = Field(default_factory=list)


class InferencePolicyV1(BaseModel):
    """primary/supporting/constraint routing per report section. No numeric pseudo-probabilities."""

    version: Literal["inference-policy-v1"] = "inference-policy-v1"
    routing: dict[ReportSection, SectionRouting]


class EvidencePackV1(BaseModel):
    declared: DeclaredEvidenceV1
    visual: VisualObservationV1 | None = None
    policy: InferencePolicyV1
    locale: str = "ko-KR"
