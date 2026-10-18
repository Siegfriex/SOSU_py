"""External research boundary: default is 'unavailable', never fabricated."""

from __future__ import annotations

from app.config import get_settings
from app.research.models import ResearchFinding, ResearchQuery
from app.research.provider import (
    FixtureResearchProvider,
    NullResearchProvider,
    get_research_provider,
    render_research_block,
)

Q = [ResearchQuery(query="릴스 저장률")]


async def test_null_provider_is_unavailable() -> None:
    result = await NullResearchProvider().research(Q)
    assert result.status == "unavailable" and result.findings == []
    block = render_research_block(result)
    assert "none available" in block and "http" not in block


def test_default_provider_is_null() -> None:
    assert get_settings().sosu_research_enabled is False
    assert isinstance(get_research_provider(), NullResearchProvider)


async def test_fixture_provider_renders_sources() -> None:
    finding = ResearchFinding(
        query="릴스 저장률",
        source_title="Example source",
        source_url="https://example.com/a",
        published_or_retrieved_date="2026-10-01",
        finding="저장은 재방문 의도의 신호로 해석된다",
        applicability="저장 수가 낮은 경우 CTA 점검",
        confidence="medium",
    )
    provider = FixtureResearchProvider(findings=[finding])
    result = await provider.research(Q)
    assert provider.seen == Q
    block = render_research_block(result)
    assert "status: ok" in block and "https://example.com/a" in block
    err = await FixtureResearchProvider(status="error").research(Q)
    assert err.status == "error" and "none available" in render_research_block(err)
