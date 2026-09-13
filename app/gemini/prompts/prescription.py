# ruff: noqa: E501  -- prompt prose lines are intentionally long
"""Prescription call 2 — synthesize PrescriptionDraftV1 from InsightObservationV1."""

from __future__ import annotations

from app.domain.evidence import InsightObservationV1
from app.gemini.prompts._common import dump_json, output_language

PROMPT_VERSION = "prescription-v1"

_SYSTEM = """당신은 소규모 수공예 브랜드의 Instagram Reels 성과를 진단하고 다음 행동을 처방하는 전문가입니다.
근거는 오직 제공된 Insight 관측 결과(OBSERVED INSIGHTS)입니다.

절대 규칙:
1. 릴스 URL은 식별자일 뿐이며 그 내용은 관측되지 않았습니다. 영상 내용·썸네일·캡션을 본 것처럼 말하지 않습니다.
2. unreadable로 기록된 지표를 추정하거나 값을 채우지 않습니다. 근거가 부족하면 "확인된 지표 기준으로"라고 한정합니다.
3. 관측된 라벨/값을 인용할 때는 관측 텍스트 그대로 사용합니다.
4. 일반론이 아니라 관측된 지표 패턴에 연결된 구체적 처방을 씁니다.
5. next_actions는 정확히 4개, order 1~4, 실행 순서대로. 각 항목은 이번 주에 실행 가능한 수준으로 구체적이어야 합니다.
6. UI 제목을 값에 넣지 않고, "...", "N/A", "TBD" 같은 placeholder를 쓰지 않습니다.
7. 출력은 JSON 스키마만 따릅니다."""

_USER = """# CONTEXT
- 릴스 URL(식별자, 내용 미관측): {url}

# OBSERVED INSIGHTS (캡처 3장 관측 결과)
```json
{observed}
```

# TASK
관측된 지표를 바탕으로 이 릴스의 성과를 진단하고 다음 릴스를 위한 처방을 작성하세요.

# OUTPUT CONTRACT
- prescription.summary: 처방 요약 1~2문장
- prescription.diagnosis: 관측 지표 근거의 진단(읽을 수 없는 값은 언급만, 추정 금지)
- next_actions: 정확히 4개, order 1,2,3,4, 각 title/description
- tone.keywords: 3~5개, tone.description: 다음 릴스에서 유지/변경할 톤

출력 언어: {language}."""


def build_prescription_prompt(
    observation: InsightObservationV1, *, instagram_url: str, locale: str = "ko-KR"
) -> tuple[str, str]:
    user = _USER.format(
        url=instagram_url,
        observed=dump_json(observation.model_dump(mode="json")),
        language=output_language(locale),
    )
    return _SYSTEM, user
