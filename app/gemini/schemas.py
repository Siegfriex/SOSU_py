"""Internal draft models used as Gemini structured-output targets, plus schema sanitizing.

Drafts mirror the public reports minus `schema_version` (set by the service, never by the
model) and with plain bounded ints for rank/order so the JSON schema stays Gemini-friendly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.diagnosis import (
    BrandSection,
    DiagnosisReportV1,
    FontSection,
    PositioningSection,
    PriorityItem,
    ReelTypeItem,
    StrengthItem,
    StructureSection,
    TargetSection,
    ToneSection,
)
from app.contracts.prescription import (
    NextActionItem,
    PrescriptionBody,
    PrescriptionReportV1,
    PrescriptionToneSection,
)


class PriorityDraft(BaseModel):
    rank: int = Field(ge=1, le=3, description="우선순위 순번 1~3. 중복 금지.")
    title: str = Field(description="우선순위 항목 제목.")
    description: str = Field(description="왜 지금 이것부터인지와 실행 방법.")


class DiagnosisDraftV1(BaseModel):
    """Gemini output target for workflow A: DiagnosisReportV1 minus schema_version."""

    model_config = ConfigDict(extra="forbid")

    brand: BrandSection
    positioning: PositioningSection
    strengths: list[StrengthItem] = Field(min_length=1, description="핵심 강점 2~4개.")
    target: TargetSection
    tone: ToneSection
    fonts: FontSection
    priorities: list[PriorityDraft] = Field(
        min_length=3, max_length=3, description="먼저 보여줄 것 정확히 3개, rank 1,2,3."
    )
    reel_types: list[ReelTypeItem] = Field(
        min_length=3, max_length=3, description="추천 릴스 유형 정확히 3개."
    )
    structure: StructureSection
    final_guidance: list[str] = Field(min_length=1, description="최종 가이드 문장 3~6개.")


class NextActionDraft(BaseModel):
    order: int = Field(ge=1, le=4, description="실행 순서 1~4. 중복 금지.")
    title: str = Field(description="다음 액션 제목.")
    description: str = Field(description="구체적인 실행 방법.")


class PrescriptionDraftV1(BaseModel):
    """Gemini output target for workflow B: PrescriptionReportV1 minus schema_version."""

    model_config = ConfigDict(extra="forbid")

    prescription: PrescriptionBody
    next_actions: list[NextActionDraft] = Field(
        min_length=4, max_length=4, description="다음 액션 정확히 4개, order 1,2,3,4."
    )
    tone: PrescriptionToneSection


def to_public_diagnosis(draft: DiagnosisDraftV1) -> DiagnosisReportV1:
    return DiagnosisReportV1(
        brand=draft.brand,
        positioning=draft.positioning,
        strengths=draft.strengths,
        target=draft.target,
        tone=draft.tone,
        fonts=draft.fonts,
        priorities=[
            PriorityItem.model_validate(p.model_dump())
            for p in sorted(draft.priorities, key=lambda p: p.rank)
        ],
        reel_types=draft.reel_types,
        structure=draft.structure,
        final_guidance=draft.final_guidance,
    )


def to_public_prescription(draft: PrescriptionDraftV1) -> PrescriptionReportV1:
    return PrescriptionReportV1(
        prescription=draft.prescription,
        next_actions=[
            NextActionItem.model_validate(a.model_dump())
            for a in sorted(draft.next_actions, key=lambda a: a.order)
        ],
        tone=draft.tone,
    )


# ------------------------------------------------------------------ JSON schema sanitizing

_DROP_KEYS = frozenset({"title", "additionalProperties", "default"})


def _sanitize(node: Any) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _DROP_KEYS:
                continue
            if key == "const":
                out["enum"] = [value]
                continue
            if key in ("properties", "$defs"):
                out[key] = {k: _sanitize(v) for k, v in value.items()}
                continue
            out[key] = _sanitize(value)
        return out
    if isinstance(node, list):
        return [_sanitize(item) for item in node]
    return node


def gemini_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema → conservative subset accepted by Gemini `response_json_schema`.

    Drops `title`/`default`/`additionalProperties`, rewrites `const` as a one-value `enum`,
    keeps `$defs`/`$ref`, `enum`, `minItems`/`maxItems`, `minimum`/`maximum`, `description`.
    """
    schema: dict[str, Any] = _sanitize(model.model_json_schema())
    return schema
