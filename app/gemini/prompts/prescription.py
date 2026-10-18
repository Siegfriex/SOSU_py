# ruff: noqa: E501  -- prompt prose lines are intentionally long
"""Prescription call 2 — synthesize PrescriptionDraftV1 from InsightObservationV1."""

from __future__ import annotations

from app.domain.evidence import InsightObservationV1
from app.gemini.prompts._common import dump_json, output_language
from app.knowledge.provider import NO_KNOWLEDGE_VERSION, render_knowledge_block
from app.research.models import ResearchResult
from app.research.provider import render_research_block

PROMPT_VERSION = "prescription-v2"

_SYSTEM = """당신은 소규모 수공예 브랜드의 Instagram Reels 성과를 진단하고 다음 행동을 처방하는 전문가입니다.
사실 근거는 오직 제공된 Insight 관측 결과(OBSERVED INSIGHTS)입니다.
GUIDEBOOK KNOWLEDGE는 지표를 해석하고 행동 우선순위를 정하는 방법에 대한 SOSU 가이드북 지식이며, EXTERNAL RESEARCH는 출처가 있는 외부 참고 정보입니다. 세 블록을 섞지 말고 구분해서 사용합니다.

절대 규칙:
1. 릴스 URL은 식별자일 뿐이며 그 내용은 관측되지 않았습니다. 영상 내용·썸네일·캡션을 본 것처럼 말하지 않습니다.
2. unreadable로 기록된 지표를 추정하거나 값을 채우지 않습니다. 근거가 부족하면 "확인된 지표 기준으로"라고 한정합니다.
3. 관측된 라벨/값을 인용할 때는 관측 텍스트 그대로 사용합니다.
4. 일반론이 아니라 관측된 지표 패턴에 연결된 구체적 처방을 씁니다.
5. next_actions는 정확히 4개, order 1~4, 실행 순서대로. 각 항목은 이번 주에 실행 가능한 수준으로 구체적이어야 합니다.
6. UI 제목을 값에 넣지 않고, "...", "N/A", "TBD" 같은 placeholder를 쓰지 않습니다.
7. 가이드북 원칙을 외부에서 검증된 플랫폼 사실이나 알고리즘 규칙처럼 단정하지 않습니다. 가이드북 규칙을 근거로 관측되지 않은 지표 값을 추정하지 않습니다.
8. EXTERNAL RESEARCH가 'none available'이면 최신 동향·통계·외부 출처를 언급하거나 만들어내지 않습니다.
9. 출력은 JSON 스키마만 따릅니다."""

_USER = """# CONTEXT
- 릴스 URL(식별자, 내용 미관측): {url}

# OBSERVED INSIGHTS (캡처 3장 관측 결과)
```json
{observed}
```

{knowledge}

{research}

# TASK
관측된 지표를 바탕으로 이 릴스의 성과를 진단하고 다음 릴스를 위한 처방을 작성하세요.
- 지표 해석(performance interpretation)과 next_actions 우선순위는 GUIDEBOOK KNOWLEDGE의 규칙을 적용하세요. 출력 JSON에 rule_id를 넣지는 마세요.
- 문장 톤은 EDITORIAL STYLE을 따르되, 수치·라벨은 OBSERVED INSIGHTS 그대로 인용합니다.

# OUTPUT CONTRACT
- prescription.summary: 처방 요약 1~2문장
- prescription.diagnosis: 관측 지표 근거의 진단(읽을 수 없는 값은 언급만, 추정 금지)
- next_actions: 정확히 4개, order 1,2,3,4, 각 title/description
- tone.keywords: 3~5개, tone.description: 다음 릴스에서 유지/변경할 톤

출력 언어: {language}."""


def build_prescription_prompt(
    observation: InsightObservationV1,
    *,
    instagram_url: str,
    locale: str = "ko-KR",
    knowledge: str | None = None,
    research: ResearchResult | None = None,
) -> tuple[str, str]:
    """`knowledge` (guidebook) and `research` (external) are separate blocks from the insights."""
    if knowledge is None:
        knowledge = render_knowledge_block(
            [], None, version=NO_KNOWLEDGE_VERSION, task="prescription"
        )
    if research is None:
        research = ResearchResult(status="unavailable", provider="null", reason="not requested")
    user = _USER.format(
        knowledge=knowledge,
        research=render_research_block(research),
        url=instagram_url,
        observed=dump_json(observation.model_dump(mode="json")),
        language=output_language(locale),
    )
    return _SYSTEM, user
