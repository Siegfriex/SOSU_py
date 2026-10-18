"""External research models (internal; not part of the public API contract)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ResearchStatus = Literal["ok", "unavailable", "error"]
ResearchConfidence = Literal["low", "medium", "high"]


class ResearchQuery(BaseModel):
    query: str = Field(min_length=1)
    task: Literal["diagnosis", "prescription"] = "prescription"
    locale: str = "ko-KR"


class ResearchFinding(BaseModel):
    query: str
    source_title: str
    source_url: str
    published_or_retrieved_date: str = Field(
        description="ISO date the source was published, or retrieved if unknown."
    )
    finding: str
    applicability: str = Field(description="How the finding applies to this request.")
    confidence: ResearchConfidence = "low"


class ResearchResult(BaseModel):
    status: ResearchStatus
    provider: str
    findings: list[ResearchFinding] = Field(default_factory=list)
    reason: str | None = None
