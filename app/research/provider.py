# ruff: noqa: E501  -- prompt prose lines are intentionally long
"""ResearchProvider boundary.

Phase 1 ships only `NullResearchProvider` (status "unavailable") and a test-only
`FixtureResearchProvider`. Live grounded search is a Phase 2 item: see docs/RESEARCH_BOUNDARY.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.config import get_settings
from app.research.models import ResearchFinding, ResearchQuery, ResearchResult


class ResearchProvider(Protocol):
    name: str

    async def research(self, queries: Sequence[ResearchQuery]) -> ResearchResult:
        """Never raises for provider failures: returns status "error" / "unavailable"."""
        ...


@dataclass(slots=True)
class NullResearchProvider:
    """Default. No external research is performed and nothing is invented."""

    reason: str = "external research disabled (SOSU_RESEARCH_ENABLED=false)"
    name: str = "null"

    async def research(self, queries: Sequence[ResearchQuery]) -> ResearchResult:
        return ResearchResult(status="unavailable", provider=self.name, reason=self.reason)


@dataclass(slots=True)
class FixtureResearchProvider:
    """Tests only: returns pre-baked findings (or a fixed status)."""

    findings: list[ResearchFinding] = field(default_factory=list)
    status: str = "ok"
    name: str = "fixture"
    seen: list[ResearchQuery] = field(default_factory=list)

    async def research(self, queries: Sequence[ResearchQuery]) -> ResearchResult:
        self.seen.extend(queries)
        if self.status != "ok":
            return ResearchResult(status="error", provider=self.name, reason="fixture error")
        return ResearchResult(status="ok", provider=self.name, findings=list(self.findings))


def get_research_provider() -> ResearchProvider:
    settings = get_settings()
    if not settings.sosu_research_enabled:
        return NullResearchProvider()
    # Phase 2: a grounded provider (google.genai types.Tool(google_search=GoogleSearch())) goes
    # here. Until it exists, enabling the flag still yields an explicit "unavailable".
    return NullResearchProvider(
        reason="research enabled but no live provider implemented (Phase 2)"
    )


def render_research_block(result: ResearchResult) -> str:
    if result.status != "ok" or not result.findings:
        why = result.reason or result.status
        return (
            "## EXTERNAL RESEARCH (status: none available)\n"
            f"외부 리서치 결과가 없습니다 ({why}). 최신 플랫폼 동향·통계·외부 출처를 언급하거나 만들어내지 마세요.\n"
            "## END EXTERNAL RESEARCH"
        )
    lines = [
        f"## EXTERNAL RESEARCH (status: ok; provider {result.provider}; cite source_url)",
        "외부 출처 기반 참고 정보입니다. 관측 지표(OBSERVED)나 가이드북 규칙과 구분해서 다루고, 출처가 있는 내용만 인용하세요.",
    ]
    for f in result.findings:
        lines.append(
            f"- {f.finding} — {f.source_title} ({f.source_url}; {f.published_or_retrieved_date}; "
            f"confidence {f.confidence}; 적용: {f.applicability})"
        )
    lines.append("## END EXTERNAL RESEARCH")
    return "\n".join(lines)
