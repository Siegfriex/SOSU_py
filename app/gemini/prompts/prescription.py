# ruff: noqa: E501  -- prompt prose lines are intentionally long
"""Prescription call 2 — synthesize PrescriptionDraftV1 from InsightObservationV1."""

from __future__ import annotations

import re

from app.domain.evidence import InsightObservationV1
from app.gemini.prompts._common import dump_json, output_language
from app.knowledge.provider import NO_KNOWLEDGE_VERSION, render_knowledge_block
from app.research.models import ResearchResult
from app.research.provider import render_research_block

PROMPT_VERSION = "prescription-v3"

_SYSTEM = """당신은 소규모 수공예 브랜드의 Instagram Reels 성과를 진단하고 다음 행동을 처방하는 전문가입니다.
사실 근거는 오직 제공된 Insight 관측 결과(OBSERVED INSIGHTS)입니다.
GUIDEBOOK KNOWLEDGE는 지표를 해석하고 행동 우선순위를 정하는 방법에 대한 SOSU 가이드북 지식이며, EXTERNAL RESEARCH는 출처가 있는 외부 참고 정보입니다. 세 블록을 섞지 말고 구분해서 사용합니다.

절대 규칙:
1. 릴스 URL과 계정명은 식별자일 뿐이며 영상 내용은 관측되지 않았습니다. 영상 내용·썸네일·캡션을 본 것처럼 말하지 않습니다.
2. unreadable로 기록된 지표를 추정하거나 값을 채우지 않습니다. 근거가 부족하면 "확인된 지표 기준으로"라고 한정합니다.
3. 관측된 라벨/값을 인용할 때는 관측 텍스트 그대로 사용합니다.
4. 일반론이 아니라 관측된 지표 패턴에 연결된 처방을 씁니다. 구체성은 지표·수치·실행 방법(촬영·편집 기법)에서 나오며, 관측되지 않은 영상 내용·제품을 지어내서 구체적으로 만들지 않습니다.
5. next_actions는 정확히 4개, order 1~4, 실행 순서대로. 각 항목은 이번 주에 실행 가능한 방법 수준으로 구체적이어야 하되, 제품·소재·공정은 특정하지 않습니다.
6. UI 제목을 값에 넣지 않고, "...", "N/A", "TBD" 같은 placeholder를 쓰지 않습니다.
7. 가이드북 원칙을 외부에서 검증된 플랫폼 사실이나 알고리즘 규칙처럼 단정하지 않습니다. 가이드북 규칙을 근거로 관측되지 않은 지표 값을 추정하지 않습니다.
8. EXTERNAL RESEARCH가 'none available'이면 최신 동향·통계·외부 출처를 언급하거나 만들어내지 않습니다.
9. 출력은 JSON 스키마만 따릅니다.

# EVIDENCE BOUNDARY (근거 경계)
이 처방은 영상을 보지 않고 Insight 스크린샷 3장만으로 작성합니다. 분석한 릴스의 장면·제품·소재·공정·편집 방식은 아무것도 관측되지 않았습니다.

사용해도 되는 근거:
- 관측된 지표 라벨과 값(OBSERVED INSIGHTS 그대로)
- 관측된 지표끼리의 단순 계산(예: 평균 시청 시간 ÷ 영상 길이로 본 시청 완료 비율). 계산임을 드러내고 원래 값도 함께 씁니다.
- 스크린샷에 보이는 화면 텍스트(캡션·문구 등). 인용할 때는 "스크린샷에 보이는 '…' 문구"처럼 화면 텍스트임을 밝히고, 영상 내용으로 바꿔 말하지 않습니다.
- GUIDEBOOK KNOWLEDGE의 권장 방법(훅 구성, 컷 길이, 조명·구도, CTA 등 촬영·편집 기법)
- 다음 영상을 위한 가설적 아이디어. 반드시 "다음 영상에서 시도해 볼 수 있는 예: …"처럼 다음 영상의 제안으로 표시하고, "이 영상의 …"처럼 분석한 영상에 귀속시키지 않습니다.

금지:
- 계정명(@…)이나 URL 경로(슬러그·shortcode)에 들어 있는 단어로 영상 내용·제품·소재·공정을 유추하는 것. 계정명·URL에 제품·소재·공정을 뜻하는 영단어가 있어도 그 번역어나 연상되는 제품·공정을 쓰지 않습니다. 계정명은 화면 텍스트(식별자)일 뿐 영상 내용이 아닙니다. 입력의 계정명은 @[계정명]으로 가려져 있습니다.
- 분석한 릴스의 보이지 않은 장면·제품·소재·공정·편집 기법을 사실처럼 서술하는 것("이 영상에서 보여준 …", "영상 속 …", "촬영하신 …").
- 제품명·소재·공정·판매 일정 등 관측되지 않은 구체 정보를 예시 카피나 CTA 문구 안에 끼워 넣는 것. 예시 문구는 제품을 특정하지 않는 일반 표현('완성작', '작업 과정', '이 작품')으로 씁니다.
- 릴스 URL을 방문했거나 영상을 시청한 것처럼 말하는 것.
- 지표 사이의 상관을 인과로 단정하는 것("~때문에 이탈했다" 대신 "~했을 가능성이 있습니다")."""

_USER = """# CONTEXT
- 릴스 URL(식별자, 내용 미관측. URL 경로의 문자열로 영상 내용을 유추하지 말 것): {url}

# OBSERVED INSIGHTS (캡처 3장 관측 결과 — 화면에 보인 지표·텍스트일 뿐, 영상 장면이 아님)
```json
{observed}
```

{knowledge}

{research}

# TASK
관측된 지표를 바탕으로 이 릴스의 성과를 진단하고 다음 릴스를 위한 처방을 작성하세요.
- 지표 해석(performance interpretation)과 next_actions 우선순위는 GUIDEBOOK KNOWLEDGE의 규칙을 적용하세요. 출력 JSON에 rule_id를 넣지는 마세요.
- 문장 톤은 EDITORIAL STYLE을 따르되, 수치·라벨은 OBSERVED INSIGHTS 그대로 인용합니다.
- EVIDENCE BOUNDARY를 지킵니다. 제출 전 각 문장을 점검하세요: 분석한 영상의 내용·제품·소재를 말하는 문장, 계정명/URL에서 유추한 단어가 있으면 지우거나 일반 표현으로 바꿉니다.

# OUTPUT CONTRACT
- prescription.summary: 처방 요약 1~2문장
- prescription.diagnosis: 관측 지표 근거의 진단(읽을 수 없는 값은 언급만, 추정 금지)
- next_actions: 정확히 4개, order 1,2,3,4, 각 title/description
- tone.keywords: 3~5개, tone.description: 다음 릴스에서 유지/변경할 톤

출력 언어: {language}."""


HANDLE_REDACTION = "@[계정명]"
_HANDLE_RE = re.compile(r"@[A-Za-z0-9._]+")


def _redact_handles(value: object) -> object:
    """Account handles are identifiers, not content — the synthesis model never sees them."""
    if isinstance(value, str):
        return _HANDLE_RE.sub(HANDLE_REDACTION, value)
    if isinstance(value, list):
        return [_redact_handles(v) for v in value]
    if isinstance(value, dict):
        return {k: _redact_handles(v) for k, v in value.items()}
    return value


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
        observed=dump_json(_redact_handles(observation.model_dump(mode="json"))),
        language=output_language(locale),
    )
    return _SYSTEM, user
