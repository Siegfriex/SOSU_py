"""Live Gemini smoke test. Skipped unless RUN_LIVE_GEMINI_TESTS=1 and a real key is configured."""

from __future__ import annotations

import os

import pytest
from app.config import get_settings
from app.domain.evidence import VisualObservationV1
from app.gemini.gateway import GenerationSpec

_settings = get_settings()

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_GEMINI_TESTS") != "1" or not _settings.gemini_configured,
    reason="live Gemini tests disabled (set RUN_LIVE_GEMINI_TESTS=1 and a real GEMINI_API_KEY)",
)


async def test_live_structured_call_smoke():
    from app.gemini.client import GoogleGenAIGateway

    gw = GoogleGenAIGateway(_settings)
    result = await gw.generate_structured(
        spec=GenerationSpec(
            model=_settings.gemini_model_observe,
            thinking=_settings.gemini_thinking_observe,
            max_output_tokens=512,
            prompt_version="live-smoke",
        ),
        system_instruction="JSON 스키마에 맞춰 짧게 답하세요.",
        user_text=(
            "이미지는 없습니다. visible_product_type은 null, 나머지 배열은 비우고 "
            "uncertainties에 '이미지 없음' 한 항목만 넣으세요."
        ),
        images=[],
        schema=VisualObservationV1,
    )
    assert isinstance(result.value, VisualObservationV1)
    assert result.usage.total_tokens is None or result.usage.total_tokens > 0
