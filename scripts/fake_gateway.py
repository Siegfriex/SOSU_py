# ruff: noqa: E501  -- Korean sample prose lines are intentionally long
"""DEV/TEST ONLY — deterministic, schema-aware GeminiGateway double for `scripts/serve_fake.py`.

Never imported by `app/`. Responses are chosen by the requested `schema` type (and by
`spec.prompt_version` for the repair call), never by a sequential queue, so a running dev server
answers repeated browser requests forever. Failure scenarios are selected per HTTP request via
`ScenarioController` (control endpoint / `X-SOSU-Fake-Scenario` header, both owned by serve_fake).

All data produced here is TEST DATA.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.domain.evidence import (
    InsightObservationV1,
    ScreenshotObservation,
    VisibleMetric,
    VisualObservationV1,
)
from app.gemini.gateway import GenerationSpec, ImagePart, StructuredResult, UsageRecord
from app.gemini.prompts import repair as repair_prompt
from app.gemini.schemas import DiagnosisDraftV1, PrescriptionDraftV1
from pydantic import BaseModel

log = logging.getLogger("sosu.fake")

SCENARIOS: tuple[str, ...] = (
    "success",
    "timeout",
    "provider_error",
    "schema_error",
    "repairable",
    "repair_failed",
    "fatal_content",
    "slow",
)
DEFAULT_SLOW_SECONDS = 5.0
MAX_SLOW_SECONDS = 170.0


# ----------------------------------------------------------------------------- scenario state


@dataclass(slots=True)
class ScenarioChoice:
    name: str = "success"
    delay_s: float = DEFAULT_SLOW_SECONDS
    slept: bool = False


@dataclass(slots=True)
class _RequestScenario:
    """Per-HTTP-request holder (set by serve_fake middleware). Resolved lazily on first model call
    so requests rejected by real validation never consume a queued scenario."""

    header: ScenarioChoice | None = None
    resolved: ScenarioChoice | None = None


_current: ContextVar[_RequestScenario | None] = ContextVar("sosu_fake_scenario", default=None)


def parse_scenario_header(raw: str | None) -> ScenarioChoice | None:
    """`X-SOSU-Fake-Scenario: repairable` or `slow:3` (delay seconds). Unknown → None."""
    if not raw:
        return None
    name, _, arg = raw.strip().partition(":")
    name = name.strip().lower()
    if name not in SCENARIOS:
        return None
    delay = DEFAULT_SLOW_SECONDS
    if arg.strip():
        try:
            delay = float(arg)
        except ValueError:
            delay = DEFAULT_SLOW_SECONDS
    return ScenarioChoice(name=name, delay_s=min(max(delay, 0.0), MAX_SLOW_SECONDS))


@dataclass(slots=True)
class ScenarioController:
    """Process-local queue: the next `times` model-backed requests use `choice`; then success."""

    _choice: ScenarioChoice = field(default_factory=ScenarioChoice)
    _remaining: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, name: str, *, times: int = 1, delay_s: float | None = None) -> None:
        if name not in SCENARIOS:
            raise ValueError(f"unknown scenario {name!r}; expected one of {SCENARIOS}")
        delay = DEFAULT_SLOW_SECONDS if delay_s is None else float(delay_s)
        with self._lock:
            self._choice = ScenarioChoice(name=name, delay_s=min(max(delay, 0.0), MAX_SLOW_SECONDS))
            self._remaining = max(int(times), 0)

    def reset(self) -> None:
        with self._lock:
            self._choice = ScenarioChoice()
            self._remaining = 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "scenario": self._choice.name if self._remaining else "success",
                "remaining": self._remaining,
                "delay_s": self._choice.delay_s,
                "available": list(SCENARIOS),
            }

    def consume(self) -> ScenarioChoice:
        with self._lock:
            if self._remaining <= 0:
                return ScenarioChoice()
            self._remaining -= 1
            return ScenarioChoice(name=self._choice.name, delay_s=self._choice.delay_s)

    def begin_request(self, header: ScenarioChoice | None) -> Any:
        """Called by middleware; returns a token for `end_request`."""
        return _current.set(_RequestScenario(header=header))

    @staticmethod
    def end_request(token: Any) -> None:
        _current.reset(token)

    def resolve(self) -> ScenarioChoice:
        holder = _current.get()
        if holder is None:  # direct gateway use outside a request (tests) → queue only
            return self.consume()
        if holder.resolved is None:
            holder.resolved = holder.header or self.consume()
        return holder.resolved


# ----------------------------------------------------------------------------- sample builders

_BRAND_RE = re.compile(r'"q1_brand_name"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _brand_from_prompt(user_text: str) -> str:
    match = _BRAND_RE.search(user_text)
    if match:
        try:
            value = json.loads(f'"{match.group(1)}"')
        except ValueError:
            value = ""
        if isinstance(value, str) and value.strip():
            return value.strip()[:40]
    return "모노유리"


def build_visual() -> VisualObservationV1:
    return VisualObservationV1(
        visible_product_type="유리 비즈를 엮어 만든 작은 키링으로 보임",
        dominant_visual_traits=[
            "투명하고 맑은 유리 비즈가 일정한 간격으로 연결됨",
            "푸른색과 호박색 계열 비즈가 번갈아 배치됨",
            "배경은 밝은 흰색 천으로 제품이 화면 중앙에 놓임",
        ],
        material_cues=["유리 비즈로 보임", "금속 고리 부분은 은색 도금으로 보임"],
        strongest_visual_signal="비즈 표면에 맺힌 작은 빛 반사점",
        possible_reel_assets=[
            "빛 각도에 따라 이동하는 반사점",
            "비즈 사이 연결 부분의 매크로 디테일",
            "흰 배경 위 색 대비",
        ],
        uncertainties=[
            "실제 크기는 비교 대상이 없어 판단하기 어려움",
            "비즈의 정확한 원산지는 사진만으로 알 수 없음",
        ],
    )


def build_insight() -> InsightObservationV1:
    return InsightObservationV1(
        screenshots=[
            ScreenshotObservation(
                source_index=0,
                visible_metrics=[
                    VisibleMetric(label="조회수", value_text="3,412"),
                    VisibleMetric(label="도달한 계정", value_text="2,870"),
                    VisibleMetric(label="평균 시청 시간", value_text="4초"),
                ],
                qualitative_notes=["처음 3초 이후 시청 유지 그래프가 급격히 하락함"],
                unreadable_regions=[],
            ),
            ScreenshotObservation(
                source_index=1,
                visible_metrics=[
                    VisibleMetric(label="좋아요", value_text="128"),
                    VisibleMetric(label="저장", value_text="9"),
                    VisibleMetric(label="공유", value_text="4"),
                ],
                qualitative_notes=["상호작용 항목 중 좋아요 비중이 가장 크게 표시됨"],
                unreadable_regions=["댓글 수 영역이 잘려 읽을 수 없음"],
            ),
            ScreenshotObservation(
                source_index=2,
                visible_metrics=[
                    VisibleMetric(label="팔로워가 아닌 사람", value_text="81.4%"),
                    VisibleMetric(label="프로필 활동", value_text="23"),
                ],
                qualitative_notes=["도달 출처 중 탐색 탭 비중이 높게 표시됨"],
                unreadable_regions=[],
            ),
        ],
        cross_image_signals=["세 장 모두 '최근 7일' 기간 표기가 동일함"],
    )


def diagnosis_draft_dict(brand: str = "모노유리") -> dict[str, Any]:
    return {
        "brand": {
            "name": brand,
            "material": "체코 유리비즈와 은색 금속 고리",
            "product": "빛을 받으면 색이 달라 보이는 유리 키링과 작은 오브제",
            "keywords": ["빛", "유리 디테일", "개별성", "손맛", "작은 반짝임"],
        },
        "positioning": {
            "summary": "빛에 따라 표정이 달라지는, 세상에 하나뿐인 작은 유리 오브제",
            "rationale": (
                "문진에서 디자인·디테일·희소성을 핵심 매력으로 선언했고, 매번 다른 색 조합으로 만든다는 차별점을 직접 적었습니다. "
                "현재 완성품 위주로만 릴스를 올리고 있어 이 차별점이 화면에 드러나지 않습니다. "
                "빛 반사와 제작 과정을 함께 보여줄 때 '개별성'이 설득력을 얻습니다."
            ),
        },
        "strengths": [
            {
                "title": "빛에 반응하는 소재감",
                "description": "정지된 완성품 사진보다 손끝에서 천천히 돌아갈 때 유리 반사가 살아납니다. 첫 장면에 움직임을 두면 스크롤을 멈추게 할 수 있습니다.",
            },
            {
                "title": "매번 다른 색 조합",
                "description": "대량 생산이 아니라는 점은 말보다 과정으로 증명됩니다. 색을 고르는 장면 자체가 희소성의 근거가 됩니다.",
            },
            {
                "title": "작고 정교한 손작업",
                "description": "비즈를 하나씩 연결하는 매크로 장면은 수공예의 밀도를 직관적으로 보여줍니다.",
            },
        ],
        "target": {
            "summary": "흔한 캐릭터 소품보다 나만의 오브제를 찾는 20~30대",
            "description": "예뻐서 사고, 나를 표현하는 물건을 갖고 싶어 하는 고객입니다. 설렘과 특별함을 느끼는 순간을 릴스 안에서 먼저 경험하게 해야 합니다.",
        },
        "tone": {
            "keywords": ["따뜻한", "섬세한", "조용한 특별함", "자연광"],
            "description": "차분한 자연광과 느린 카메라 움직임, 과장 없는 짧은 자막으로 유아적이거나 값싸 보이는 인상을 피합니다. 배경음은 잔잔한 어쿠스틱 계열이 어울립니다.",
        },
        "fonts": {
            "title": "단정한 산세리프, 중간 이상 굵기",
            "subtitle": "가독성 높은 산세리프 레귤러, 넉넉한 자간",
            "reason": "따뜻함과 특별함을 유지하면서도 장식적인 서체가 주는 유아적인 인상을 피하기 위한 방향입니다.",
        },
        "priorities": [
            {
                "rank": 1,
                "title": "햇빛을 통과하는 유리",
                "description": "첫 3초 안에 제품을 천천히 돌려 반사 변화를 보여주세요. 가장 강한 시각 자산을 훅으로 씁니다.",
            },
            {
                "rank": 2,
                "title": "손으로 연결하는 과정",
                "description": "비즈를 고르고 하나씩 연결하는 손 클로즈업으로 '매번 다르다'는 차별점을 증명합니다.",
            },
            {
                "rank": 3,
                "title": "포장 전 마지막 점검",
                "description": "포장하기 전 햇빛에 비춰보는 장면을 마무리 컷으로 써서 정성과 품질 확인을 함께 전달합니다.",
            },
        ],
        "reel_types": [
            {
                "name": "제작 디테일형",
                "reason": "현재 완성품 위주 콘텐츠에서 보이지 않던 제작 차별점을 보완합니다. 손과 재료만으로 구성해 촬영 부담이 적습니다.",
            },
            {
                "name": "빛 변화 무드형",
                "reason": "빛에 따른 색 변화라는 핵심 메시지를 자막과 잔잔한 음악만으로 전달할 수 있습니다.",
            },
            {
                "name": "비포·애프터 조합형",
                "reason": "낱개 비즈에서 완성 키링까지의 변화를 보여줘 아이디어 고갈 문제를 매주 반복 가능한 포맷으로 해결합니다.",
            },
        ],
        "structure": {
            "hook_0_3": "창가 햇빛 아래에서 키링을 천천히 돌려 색이 바뀌는 순간을 클로즈업, 자막 '빛을 받으면 달라져요'",
            "body_3_10": "트레이 위 비즈 중에서 이번 주 색 조합을 고르는 손 클로즈업",
            "body_10_20": "비즈를 하나씩 연결하는 과정을 3~4컷으로 빠르게 이어 붙이고, 자막으로 '같은 조합은 다시 만들지 않아요'",
            "close_20_27": "완성품을 포장 전에 햇빛에 비춰보며 마지막으로 점검하는 장면",
            "cta_27_30": "자막 '이번 주 조합은 프로필 링크에서' 와 함께 완성품 정지 컷",
        },
        "final_guidance": [
            "매주 한 가지 색 조합을 정해 제작 과정 릴스를 먼저 올리세요.",
            "첫 3초는 항상 움직이는 빛 반사 장면으로 시작하세요.",
            "설명은 짧은 자막과 손동작으로 전달하고, 한 화면에 한 문장만 두세요.",
            "완성품 단독 릴스는 제작 과정 릴스 다음 날 이어서 올려 흐름을 만드세요.",
        ],
    }


def prescription_draft_dict() -> dict[str, Any]:
    return {
        "prescription": {
            "summary": "탐색 탭을 통한 도달은 충분하지만 첫 3초 이후 이탈이 커서 저장·공유로 이어지지 않습니다. 다음 릴스는 훅과 저장 유도를 함께 바꿔야 합니다.",
            "diagnosis": (
                "조회수 3,412, 도달한 계정 2,870으로 노출은 확보되었고 팔로워가 아닌 사람 비중이 81.4%로 신규 도달이 큽니다. "
                "반면 평균 시청 시간이 4초이고 저장 9, 공유 4로 관찰되어 초반 이후 관심이 유지되지 않습니다. "
                "댓글 수는 화면이 잘려 읽을 수 없어 판단에서 제외했습니다."
            ),
        },
        "next_actions": [
            {
                "order": 1,
                "title": "첫 1초 훅 교체",
                "description": "완성품 정지 컷 대신 빛 반사가 움직이는 장면으로 시작해 탐색 탭 유입자의 시선을 붙잡으세요.",
            },
            {
                "order": 2,
                "title": "3초 지점에 질문 자막",
                "description": "'이 색, 어떻게 나왔을까요?' 같은 질문 자막을 3초 지점에 넣어 이탈 구간을 넘기게 하세요.",
            },
            {
                "order": 3,
                "title": "저장 유도 마무리",
                "description": "마지막 3초에 '조합 저장해두기' 자막과 완성품 정지 컷을 넣어 저장 행동을 명확히 요청하세요.",
            },
            {
                "order": 4,
                "title": "2주간 같은 시간 게시",
                "description": "같은 요일·시간에 2주간 게시해 평균 시청 시간과 저장 수를 비교할 기준 데이터를 만드세요.",
            },
        ],
        "tone": {
            "keywords": ["차분한", "섬세한", "신뢰감", "자연광"],
            "description": "현재의 차분한 분위기는 유지하되 초반 컷 전환 속도만 높이세요. 자막은 짧고 단정하게 유지합니다.",
        },
    }


def _repairable(draft: dict[str, Any], key: str) -> dict[str, Any]:
    """Schema-valid but semantically REPAIRABLE (duplicate rank/order)."""
    broken = json.loads(json.dumps(draft))
    items = broken[key]
    field_name = "rank" if key == "priorities" else "order"
    items[1][field_name] = items[0][field_name]
    return broken


def _fatal_diagnosis() -> DiagnosisDraftV1:
    p = "..."
    return DiagnosisDraftV1.model_validate(
        {
            "brand": {"name": p, "material": p, "product": p, "keywords": [p]},
            "positioning": {"summary": p, "rationale": p},
            "strengths": [{"title": p, "description": p}],
            "target": {"summary": p, "description": p},
            "tone": {"keywords": [p], "description": p},
            "fonts": {"title": p, "subtitle": p, "reason": p},
            "priorities": [{"rank": i, "title": p, "description": p} for i in (1, 2, 3)],
            "reel_types": [{"name": p, "reason": p} for _ in range(3)],
            "structure": {
                k: p for k in ("hook_0_3", "body_3_10", "body_10_20", "close_20_27", "cta_27_30")
            },
            "final_guidance": [p],
        }
    )


def _fatal_prescription() -> PrescriptionDraftV1:
    p = "N/A"
    return PrescriptionDraftV1.model_validate(
        {
            "prescription": {"summary": p, "diagnosis": p},
            "next_actions": [{"order": i, "title": p, "description": p} for i in (1, 2, 3, 4)],
            "tone": {"keywords": [p], "description": p},
        }
    )


# ----------------------------------------------------------------------------- gateway


@dataclass(slots=True)
class FakeCall:
    schema: str
    prompt_version: str
    scenario: str
    user_text: str
    system_instruction: str


@dataclass(slots=True)
class ScenarioFakeGateway:
    """Deterministic GeminiGateway double. TEST DATA ONLY."""

    controller: ScenarioController = field(default_factory=ScenarioController)
    calls: list[FakeCall] = field(default_factory=list)
    max_calls_kept: int = 50

    async def generate_structured(
        self,
        *,
        spec: GenerationSpec,
        system_instruction: str,
        user_text: str,
        images: list[ImagePart],
        schema: type[Any],
    ) -> StructuredResult[Any]:
        choice = self.controller.resolve()
        is_repair = spec.prompt_version == repair_prompt.PROMPT_VERSION
        is_synthesis = schema in (DiagnosisDraftV1, PrescriptionDraftV1) and not is_repair
        self.calls.append(
            FakeCall(
                schema=schema.__name__,
                prompt_version=spec.prompt_version,
                scenario=choice.name,
                user_text=user_text,
                system_instruction=system_instruction,
            )
        )
        del self.calls[: -self.max_calls_kept]
        log.info(
            "FAKE GATEWAY — TEST DATA schema=%s prompt=%s scenario=%s images=%d",
            schema.__name__,
            spec.prompt_version,
            choice.name,
            len(images),
        )

        name = choice.name
        if name == "slow" and not choice.slept:
            # Sleep once per request (first model call) so stale-response UIs can be tested.
            choice.slept = True
            await asyncio.sleep(choice.delay_s)
        if name == "timeout":
            raise SosuError(ErrorCode.MODEL_TIMEOUT, "Model request timed out.", details=[])
        if name == "provider_error":
            raise SosuError(
                ErrorCode.MODEL_PROVIDER_ERROR,
                "Model provider is temporarily unavailable.",
                details=[{"status": 503}],
            )
        if name == "schema_error" and is_synthesis:
            raise SosuError(
                ErrorCode.MODEL_SCHEMA_ERROR,
                "Model output did not match the expected schema.",
                details=[{"schema": schema.__name__, "locations": ["priorities"]}],
            )
        return StructuredResult(
            value=self._value(schema, name, is_repair=is_repair, user_text=user_text),
            usage=UsageRecord(total_tokens=0),
            raw_json=None,
        )

    @staticmethod
    def _value(schema: type[Any], scenario: str, *, is_repair: bool, user_text: str) -> BaseModel:
        if schema is VisualObservationV1:
            return build_visual()
        if schema is InsightObservationV1:
            return build_insight()
        if schema is DiagnosisDraftV1:
            good = diagnosis_draft_dict(_brand_from_prompt(user_text))
            if scenario == "fatal_content":
                return _fatal_diagnosis()
            if (scenario == "repairable" and not is_repair) or scenario == "repair_failed":
                return DiagnosisDraftV1.model_validate(_repairable(good, "priorities"))
            return DiagnosisDraftV1.model_validate(good)
        if schema is PrescriptionDraftV1:
            good = prescription_draft_dict()
            if scenario == "fatal_content":
                return _fatal_prescription()
            if (scenario == "repairable" and not is_repair) or scenario == "repair_failed":
                return PrescriptionDraftV1.model_validate(_repairable(good, "next_actions"))
            return PrescriptionDraftV1.model_validate(good)
        raise SosuError(
            ErrorCode.MODEL_SCHEMA_ERROR,
            "Fake gateway has no sample for this schema.",
            details=[{"schema": schema.__name__}],
        )
