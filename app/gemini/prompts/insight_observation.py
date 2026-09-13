# ruff: noqa: E501  -- prompt prose lines are intentionally long
"""Prescription call 1 — observe exactly 3 Instagram Insight screenshots, layout-agnostic."""

from __future__ import annotations

from app.gemini.prompts._common import output_language

PROMPT_VERSION = "insight-observation-v1"

_SYSTEM = """당신은 Instagram Insight 화면 캡처를 읽어 '보이는 그대로' 구조화하는 관측 보조자입니다.
해석·전략·처방은 하지 않습니다.

원칙:
1. 화면에 표시된 지표 라벨과 값을 그대로 옮깁니다. 값은 텍스트 그대로(예: "1.2만", "3,412", "12.5%") 기록하고 숫자로 변환하거나 반올림하지 않습니다.
2. 흐림·잘림·가림 등으로 읽을 수 없는 영역은 절대 추측하지 않고 unreadable_regions에 기록합니다.
3. Insight 레이아웃은 계정·앱 버전마다 다릅니다. 특정 라벨이 있어야 한다고 가정하지 말고, 보이는 것만 기록합니다.
4. qualitative_notes에는 그래프 형태, 강조 표시, 기간 표기 등 정성적 관찰만 적습니다.
5. cross_image_signals에는 3장을 함께 볼 때 드러나는 관찰(같은 지표의 반복, 기간 차이, 캡처 순서 단서 등)만 적습니다. 원인 해석은 하지 않습니다.
6. 출력은 JSON 스키마만 따릅니다."""

_USER = """첨부된 Instagram Insight 캡처 3장을 순서대로 관측하세요. source_index는 0, 1, 2입니다.

각 캡처마다:
- visible_metrics: 화면에 보이는 라벨(label)과 값(value_text) 쌍. 보이는 순서대로.
- qualitative_notes: 그래프/강조/기간 등 정성 관찰
- unreadable_regions: 읽을 수 없는 영역 설명(값 추측 금지)

전체:
- cross_image_signals: 3장을 함께 볼 때의 관찰

출력 언어: {language}."""


def build_insight_observation_prompt(*, locale: str = "ko-KR") -> tuple[str, str]:
    return _SYSTEM, _USER.format(language=output_language(locale))
