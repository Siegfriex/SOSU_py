"""Guidebook KnowledgePack v1 models (internal; not part of the public API contract).

Produced offline from the SOSU guidebook PDF (knowledge/guidebook/knowledgepack.v1.json).
The service never parses the PDF; it only loads and validates this JSON once per process.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

KnowledgeTask = Literal["diagnosis", "prescription"]

RuleCategory = Literal[
    "reels_fundamentals",
    "reel_types",
    "combination",
    "ideation",
    "storyboard",
    "equipment",
    "lighting",
    "composition",
    "camera_angle",
    "editing_pacing",
    "video_length",
    "music_sound",
    "hook",
    "caption",
    "cta",
    "performance_interpretation",
    "brand_strategy",
]

EvidenceType = Literal["guidebook_principle", "guidebook_example", "author_experience"]


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    filename: str
    sha256: str
    pages: int = Field(ge=0)


class StyleGuide(BaseModel):
    model_config = ConfigDict(extra="ignore")

    voice: list[str] = Field(default_factory=list)
    do: list[str] = Field(default_factory=list)
    dont: list[str] = Field(default_factory=list)
    example_phrases: list[str] = Field(default_factory=list)


class GuidebookRule(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    rule_id: str = Field(pattern=r"^GB-[A-Z0-9_]+-\d{3,}$")
    category: RuleCategory
    source_pages: list[int] = Field(default_factory=list)
    source_section: str = ""
    principle: str = Field(min_length=1)
    applicability: list[KnowledgeTask] = Field(min_length=1)
    recommended_action: str = ""
    exceptions_or_cautions: str | None = None
    evidence_type: EvidenceType = "guidebook_principle"
    tags: list[str] = Field(default_factory=list)
    priority: Literal[1, 2, 3] = 2


class KnowledgePackV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["1.0"]
    pack_id: str
    version: str = Field(min_length=1)
    source: KnowledgeSource
    style: StyleGuide = Field(default_factory=StyleGuide)
    rules: list[GuidebookRule] = Field(default_factory=list)
    # task → report_section → categories relevant to that section
    task_mapping: dict[KnowledgeTask, dict[str, list[RuleCategory]]] = Field(default_factory=dict)
