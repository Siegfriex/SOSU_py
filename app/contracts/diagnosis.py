"""Workflow A — survey → DiagnosisReportV1 (public contract)."""

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

# Hard ingress bound for a single natural-language answer (deterministic, no rewriting).
MAX_TEXT_LEN = 4000
MAX_CHOICES = 3

_Text = str | None


class SurveyAnswersV1(BaseModel):
    """Survey answers. Every field is optional (partial completion allowed).

    `extra="forbid"` guarantees that unknown fields — in particular `q19_*` — are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    q1_brand_name: _Text = Field(default=None, max_length=MAX_TEXT_LEN)
    q2_product_category: _Text = Field(default=None, max_length=MAX_TEXT_LEN)
    q3_hero_product: _Text = Field(default=None, max_length=MAX_TEXT_LEN)
    q4_materials: _Text = Field(default=None, max_length=MAX_TEXT_LEN)
    q5_material_reason: _Text = Field(default=None, max_length=MAX_TEXT_LEN)

    q6_product_appeals: list[ProductAppeal] = Field(default_factory=list, max_length=MAX_CHOICES)

    q7_differentiation: _Text = Field(default=None, max_length=MAX_TEXT_LEN)
    q8_target_customer: _Text = Field(default=None, max_length=MAX_TEXT_LEN)

    q9_purchase_motives: list[PurchaseMotive] = Field(default_factory=list, max_length=MAX_CHOICES)
    q10_desired_emotions: list[DesiredEmotion] = Field(default_factory=list, max_length=MAX_CHOICES)
    q11_brand_attributes: list[BrandAttribute] = Field(default_factory=list, max_length=MAX_CHOICES)

    q12_avoidance: _Text = Field(default=None, max_length=MAX_TEXT_LEN)
    q13_motif: _Text = Field(default=None, max_length=MAX_TEXT_LEN)
    q14_primary_message: _Text = Field(default=None, max_length=MAX_TEXT_LEN)
    q15_interesting_process: _Text = Field(default=None, max_length=MAX_TEXT_LEN)

    q16_pain_points: list[InstagramPainPoint] = Field(default_factory=list, max_length=MAX_CHOICES)
    q17_current_formats: list[CurrentReelFormat] = Field(
        default_factory=list, max_length=MAX_CHOICES
    )

    q18_disclosure: CreatorDisclosure | None = None

    q20_must_show: _Text = Field(default=None, max_length=MAX_TEXT_LEN)


class SurveyDiagnosisRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    locale: str = Field(default="ko-KR", max_length=16)
    answers: SurveyAnswersV1


# ---------------------------------------------------------------- report (public output)


class BrandSection(BaseModel):
    name: str = Field(description="브랜드명. 미제공 시 제품/소재 기반의 서술적 명칭.")
    material: str = Field(description="핵심 소재를 한 구절로.")
    product: str = Field(description="대표 제품을 한 구절로.")
    keywords: list[str] = Field(description="브랜드를 요약하는 핵심 키워드 3~6개.")


class PositioningSection(BaseModel):
    summary: str = Field(description="브랜드 포지셔닝 한 문장.")
    rationale: str = Field(description="포지셔닝 근거. 설문 답변과 관찰 근거를 인용.")


class StrengthItem(BaseModel):
    title: str = Field(description="강점 제목(짧게).")
    description: str = Field(description="강점 설명과 릴스에서 보여주는 방법.")


class TargetSection(BaseModel):
    summary: str = Field(description="핵심 타깃 한 문장.")
    description: str = Field(description="타깃의 구매 동기와 감정적 니즈 설명.")


class ToneSection(BaseModel):
    keywords: list[str] = Field(description="톤앤매너 키워드 3~5개.")
    description: str = Field(description="영상 분위기/색감/속도감 등 톤 설명.")


class FontSection(BaseModel):
    title: str = Field(description="제목용 서체 방향(예: 굵은 산세리프, 손글씨 계열).")
    subtitle: str = Field(description="본문/자막용 서체 방향.")
    reason: str = Field(description="서체 선택 이유(톤/피해야 할 인상과 연결).")


class PriorityItem(BaseModel):
    rank: Literal[1, 2, 3]
    title: str = Field(description="우선순위 항목 제목.")
    description: str = Field(description="왜 지금 이것부터인지와 실행 방법.")


class ReelTypeItem(BaseModel):
    name: str = Field(description="추천 릴스 유형 이름.")
    reason: str = Field(description="이 브랜드에 이 유형이 맞는 이유. 제작자 노출 제약을 준수.")


class StructureSection(BaseModel):
    hook_0_3: str = Field(description="0~3초 훅.")
    body_3_10: str = Field(description="3~10초 전개.")
    body_10_20: str = Field(description="10~20초 전개.")
    close_20_27: str = Field(description="20~27초 마무리.")
    cta_27_30: str = Field(description="27~30초 CTA.")


class DiagnosisReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["diagnosis.v1"] = "diagnosis.v1"
    brand: BrandSection
    positioning: PositioningSection
    strengths: list[StrengthItem] = Field(min_length=1)
    target: TargetSection
    tone: ToneSection
    fonts: FontSection
    priorities: list[PriorityItem] = Field(min_length=3, max_length=3)
    reel_types: list[ReelTypeItem] = Field(min_length=3, max_length=3)
    structure: StructureSection
    final_guidance: list[str] = Field(min_length=1)
