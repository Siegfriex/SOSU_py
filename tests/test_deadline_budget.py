"""RD-6: remaining-budget propagation (observe → synthesis → repair) under the request deadline.

Production numbers are 180 s deadline / 60-90-40 s stages (sum 190 > 180). These tests run the
same pipeline at a tiny scale with a gateway that honours `spec.timeout_seconds` like the real
GoogleGenAIGateway (asyncio.wait_for), so they prove the ordering properties without live calls.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any

import pytest
from app.api.deps import get_diagnosis_service
from app.config import Settings
from app.contracts.diagnosis import SurveyDiagnosisRequestV1
from app.contracts.envelope import ErrorCode
from app.contracts.prescription import PrescriptionRequestV1
from app.domain.errors import SosuError
from app.domain.evidence import VisualObservationV1
from app.gemini.client import GoogleGenAIGateway
from app.gemini.gateway import GenerationSpec, ImagePart, StructuredResult
from app.gemini.prompts import (
    diagnosis,
    insight_observation,
    prescription,
    repair,
    visual_observation,
)
from app.main import create_app
from app.services.deadline import budget_spec, remaining_seconds, stage_timeout, with_deadline
from app.services.diagnosis_service import DiagnosisService
from app.services.prescription_service import PrescriptionService
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from tests.api_samples import diagnosis_request_dict
from tests.fakes import (
    FakeGateway,
    fake_image,
    sample_diagnosis_draft,
    sample_insight,
    sample_prescription_draft,
    sample_visual,
)
from tests.helpers import sample_diagnosis_request_dict, sample_prescription_request_dict

SPEC = GenerationSpec(
    model="m", thinking="low", max_output_tokens=256, prompt_version="p", timeout_seconds=60
)


def _settings(**overrides: Any) -> Settings:
    return Settings(gemini_api_key="test-key-not-real", **overrides)  # type: ignore[arg-type]


@dataclass(slots=True)
class TimedGateway:
    """Each call takes `delays[prompt_version]` s but is cut at spec.timeout_seconds (like
    GoogleGenAIGateway's asyncio.wait_for) → MODEL_TIMEOUT. Records (prompt, timeout) per call."""

    delays: dict[str, float]
    inner: FakeGateway
    calls: list[tuple[str, float]] = field(default_factory=list)

    async def generate_structured(
        self,
        *,
        spec: GenerationSpec,
        system_instruction: str,
        user_text: str,
        images: list[ImagePart],
        schema: type[Any],
    ) -> StructuredResult[Any]:
        self.calls.append((spec.prompt_version, spec.timeout_seconds))
        try:
            await asyncio.wait_for(
                asyncio.sleep(self.delays.get(spec.prompt_version, 0.0)), spec.timeout_seconds
            )
        except TimeoutError:
            raise SosuError(ErrorCode.MODEL_TIMEOUT, "Model request timed out.") from None
        return await self.inner.generate_structured(
            spec=spec,
            system_instruction=system_instruction,
            user_text=user_text,
            images=images,
            schema=schema,
        )

    def prompts(self) -> list[str]:
        return [p for p, _ in self.calls]

    def timeout_of(self, prompt: str) -> float:
        return dict(self.calls)[prompt]


def _repairable_draft() -> Any:
    bad = sample_diagnosis_draft()
    bad.reel_types[
        0
    ].reason = "내레이션으로 제작 과정을 설명합니다"  # violates face_only → REPAIRABLE
    return bad


def _req() -> SurveyDiagnosisRequestV1:
    return SurveyDiagnosisRequestV1.model_validate(sample_diagnosis_request_dict())


# ------------------------------------------------------------------ unit: budget arithmetic


async def test_outside_deadline_spec_is_unchanged() -> None:
    assert remaining_seconds() is None
    assert budget_spec(SPEC) is SPEC
    assert stage_timeout(40, stage="x") == 40


async def test_with_plenty_of_budget_stage_timeout_is_kept() -> None:
    async def body() -> GenerationSpec:
        return budget_spec(SPEC)

    spec = await with_deadline(body(), seconds=180, request_id="t")
    assert spec.timeout_seconds == 60  # 180 − 2 margin ≫ 60


async def test_stage_timeout_is_capped_by_remaining_minus_margin() -> None:
    async def body() -> float:
        await asyncio.sleep(0.5)
        return budget_spec(replace(SPEC, timeout_seconds=0.9)).timeout_seconds

    t = await with_deadline(body(), seconds=1.0, request_id="t")
    # remaining ≈ 0.5, margin = 5 % of 1.0 = 0.05 → ≈ 0.45 (< stage 0.9)
    assert 0.3 < t < 0.46


async def test_budget_below_minimum_raises_model_timeout_without_starting_stage() -> None:
    async def body() -> GenerationSpec:
        await asyncio.sleep(0.9)
        return budget_spec(replace(SPEC, timeout_seconds=0.5, prompt_version="stage-x"))

    with pytest.raises(SosuError) as exc:
        await with_deadline(body(), seconds=1.0, request_id="t")
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    assert exc.value.http_status == 504
    assert exc.value.details == [{"deadline_seconds": 1.0, "stage": "stage-x"}]


# ------------------------------------------------------------------ pipeline at tiny scale

TINY = dict(
    sosu_request_deadline_seconds=0.6,
    gemini_timeout_observe=0.3,
    gemini_timeout_synthesis=0.4,
    gemini_timeout_repair=0.2,
)


async def test_slow_observation_gives_model_timeout_before_deadline() -> None:
    gw = TimedGateway(
        delays={visual_observation.PROMPT_VERSION: 5.0},
        inner=FakeGateway(responses=[sample_visual(), sample_diagnosis_draft()]),
    )
    started = time.monotonic()
    with pytest.raises(SosuError) as exc:
        await DiagnosisService(gw, settings=_settings(**TINY)).run(
            _req(), fake_image(), request_id="t"
        )
    elapsed = time.monotonic() - started
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    assert elapsed < 0.6
    assert gw.prompts() == [visual_observation.PROMPT_VERSION]


async def test_synthesis_gets_reduced_timeout_after_slow_observation() -> None:
    gw = TimedGateway(
        delays={visual_observation.PROMPT_VERSION: 0.25},
        inner=FakeGateway(responses=[sample_visual(), sample_diagnosis_draft()]),
    )
    report = await DiagnosisService(gw, settings=_settings(**TINY)).run(
        _req(), fake_image(), request_id="t"
    )
    assert report.schema_version == "diagnosis.v1"
    assert gw.timeout_of(visual_observation.PROMPT_VERSION) == pytest.approx(0.3)
    # remaining ≈ 0.6 − 0.25 = 0.35, minus margin 0.03 → ≈ 0.32 < configured 0.4
    synth = gw.timeout_of(diagnosis.PROMPT_VERSION)
    assert 0.2 < synth < 0.34


async def test_prescription_synthesis_gets_reduced_timeout_after_slow_observation() -> None:
    gw = TimedGateway(
        delays={insight_observation.PROMPT_VERSION: 0.25},
        inner=FakeGateway(responses=[sample_insight(), sample_prescription_draft()]),
    )
    req = PrescriptionRequestV1.model_validate(sample_prescription_request_dict())
    report = await PrescriptionService(gw, settings=_settings(**TINY)).run(
        req, [fake_image()] * 3, request_id="t"
    )
    assert report.schema_version == "prescription.v1"
    assert gw.timeout_of(insight_observation.PROMPT_VERSION) == pytest.approx(0.3)
    assert 0.2 < gw.timeout_of(prescription.PROMPT_VERSION) < 0.34


async def test_repair_never_starts_when_budget_is_exhausted() -> None:
    settings = _settings(
        sosu_request_deadline_seconds=1.2,
        gemini_timeout_observe=0.6,
        gemini_timeout_synthesis=0.8,
        gemini_timeout_repair=0.4,
    )
    gw = TimedGateway(
        delays={visual_observation.PROMPT_VERSION: 0.3, diagnosis.PROMPT_VERSION: 0.75},
        inner=FakeGateway(
            responses=[sample_visual(), _repairable_draft(), sample_diagnosis_draft()]
        ),
    )
    with pytest.raises(SosuError) as exc:
        await DiagnosisService(gw, settings=settings).run(_req(), fake_image(), request_id="t")
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    # elapsed ≈ 1.05 → usable 0.15 − 0.06 margin < 0.12 minimum → refused before the call
    assert exc.value.details == [{"deadline_seconds": 1.2, "stage": repair.PROMPT_VERSION}]
    assert repair.PROMPT_VERSION not in gw.prompts()


async def test_worst_case_60_90_40_scaled_is_cut_before_deadline() -> None:
    # 180/60/90/40 s scaled by 1/100. Observation and synthesis each take almost their whole
    # stage timeout, then a REPAIRABLE draft forces repair: 0.6 + 0.9 + 0.4 = 1.9 > 1.8.
    settings = _settings(
        sosu_request_deadline_seconds=1.8,
        gemini_timeout_observe=0.6,
        gemini_timeout_synthesis=0.9,
        gemini_timeout_repair=0.4,
    )
    gw = TimedGateway(
        delays={
            visual_observation.PROMPT_VERSION: 0.58,
            diagnosis.PROMPT_VERSION: 0.88,
            repair.PROMPT_VERSION: 0.39,
        },
        inner=FakeGateway(
            responses=[sample_visual(), _repairable_draft(), sample_diagnosis_draft()]
        ),
    )
    started = time.monotonic()
    with pytest.raises(SosuError) as exc:
        await DiagnosisService(gw, settings=settings).run(_req(), fake_image(), request_id="t")
    elapsed = time.monotonic() - started
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    # Repair is capped to end at deadline − margin (≈1.71); 0.05 s tolerance for scheduler jitter.
    # Either way it is a structured error far before the scaled Vercel kill at 2.0 s.
    assert elapsed < 1.85
    assert gw.timeout_of(repair.PROMPT_VERSION) < 0.4  # repair got only the remaining budget


# ------------------------------------------------------------------ real gateway: cancel / retry


class _Aio:
    def __init__(self, behaviour: Any) -> None:
        self.behaviour = behaviour
        self.calls = 0
        self.cancelled = False

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls += 1
        try:
            return await self.behaviour(self.calls)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def _real_gateway(behaviour: Any) -> tuple[GoogleGenAIGateway, _Aio]:
    aio = _Aio(behaviour)
    client = SimpleNamespace(aio=SimpleNamespace(models=aio))
    return GoogleGenAIGateway(_settings(), client=client), aio  # type: ignore[arg-type]


async def _gen(gw: GoogleGenAIGateway, spec: GenerationSpec) -> Any:
    return await gw.generate_structured(
        spec=spec, system_instruction="s", user_text="u", images=[], schema=VisualObservationV1
    )


async def test_deadline_cancels_in_flight_provider_call() -> None:
    async def hang(n: int) -> Any:
        await asyncio.sleep(10)

    gw, aio = _real_gateway(hang)
    started = time.monotonic()
    with pytest.raises(SosuError) as exc:
        # Stage timeout 60 s, but the request deadline is 0.1 s: the outer bound wins.
        await with_deadline(_gen(gw, SPEC), seconds=0.1, request_id="t")
    assert time.monotonic() - started < 1.0
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    assert exc.value.details == [{"deadline_seconds": 0.1}]
    assert aio.cancelled is True
    assert aio.calls == 1


async def test_retry_is_skipped_when_stage_budget_is_spent() -> None:
    async def slow_503(n: int) -> Any:
        await asyncio.sleep(0.25)
        raise genai_errors.APIError(503, {"error": {"message": "x", "status": "UNAVAILABLE"}})

    gw, aio = _real_gateway(slow_503)
    started = time.monotonic()
    with pytest.raises(SosuError) as exc:
        await _gen(gw, replace(SPEC, timeout_seconds=0.3))
    # 0.25 s spent + ≥0.5 s backoff > 0.3 s stage budget → no second provider call.
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    assert aio.calls == 1
    assert time.monotonic() - started < 1.0


async def test_retry_attempt_only_gets_the_rest_of_the_stage_budget() -> None:
    async def fail_then_hang(n: int) -> Any:
        if n == 1:
            raise genai_errors.APIError(503, {"error": {"message": "x", "status": "UNAVAILABLE"}})
        await asyncio.sleep(10)

    gw, aio = _real_gateway(fail_then_hang)
    started = time.monotonic()
    with pytest.raises(SosuError) as exc:
        await _gen(gw, replace(SPEC, timeout_seconds=1.0))
    elapsed = time.monotonic() - started
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    assert aio.calls == 2
    assert aio.cancelled is True
    assert elapsed < 1.2  # retry fit inside the 1.0 s stage timeout (not 0.5 backoff + 1.0)


# ------------------------------------------------------------------ HTTP: 504 envelope


def test_http_deadline_returns_504_model_timeout_envelope() -> None:
    gw = TimedGateway(
        delays={diagnosis.PROMPT_VERSION: 5.0},
        inner=FakeGateway(responses=[sample_diagnosis_draft()]),
    )
    service = DiagnosisService(gw, settings=_settings(**TINY))
    app = create_app()
    app.dependency_overrides[get_diagnosis_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    started = time.monotonic()
    resp = client.post(
        "/api/v1/diagnosis",
        data={"payload": json.dumps(diagnosis_request_dict(), ensure_ascii=False)},
    )
    assert time.monotonic() - started < 2.0
    assert resp.status_code == 504, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["contract_version"] == "1.0"
    assert body["request_id"]
    assert body["error"]["code"] == "MODEL_TIMEOUT"
    assert body["error"]["retryable"] is True
    assert isinstance(body["error"]["details"], list)
    assert gw.prompts() == [diagnosis.PROMPT_VERSION]
