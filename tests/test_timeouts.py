"""Timeout hierarchy: observe 45s / synthesis 90s / repair 40s inside an overall 180s deadline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from app.config import Settings
from app.contracts.diagnosis import SurveyDiagnosisRequestV1  # noqa: I001
from app.contracts.envelope import ErrorCode
from app.contracts.prescription import PrescriptionRequestV1
from app.domain.errors import SosuError
from app.gemini.gateway import GenerationSpec, ImagePart, StructuredResult, UsageRecord
from app.gemini.prompts import (
    diagnosis,
    insight_observation,
    prescription,
    repair,
    visual_observation,
)
from app.services.deadline import with_deadline
from app.services.diagnosis_service import DiagnosisService
from app.services.prescription_service import PrescriptionService

from tests.fakes import (
    FakeGateway,
    fake_image,
    sample_diagnosis_draft,
    sample_insight,
    sample_prescription_draft,
    sample_visual,
)
from tests.helpers import sample_diagnosis_request_dict, sample_prescription_request_dict

BASE = dict(gemini_api_key="test-key-not-real")


def _settings(**overrides: Any) -> Settings:
    return Settings(**BASE, **overrides)  # type: ignore[arg-type]


# ------------------------------------------------------------------ defaults / hierarchy


def test_default_timeout_hierarchy_matches_owner_decision() -> None:
    s = Settings()
    assert s.gemini_timeout_observe == 45.0
    assert s.gemini_timeout_synthesis == 90.0
    assert s.gemini_timeout_repair == 40.0
    assert s.sosu_request_deadline_seconds == 180.0


def test_stage_timeouts_fit_inside_overall_deadline() -> None:
    s = Settings()
    worst_case = s.gemini_timeout_observe + s.gemini_timeout_synthesis + s.gemini_timeout_repair
    assert worst_case <= s.sosu_request_deadline_seconds
    assert max(s.gemini_timeout_observe, s.gemini_timeout_synthesis, s.gemini_timeout_repair) < (
        s.sosu_request_deadline_seconds
    )


def test_env_overrides_are_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_TIMEOUT_OBSERVE", "12")
    monkeypatch.setenv("SOSU_REQUEST_DEADLINE_SECONDS", "99")
    s = Settings()
    assert s.gemini_timeout_observe == 12.0
    assert s.sosu_request_deadline_seconds == 99.0


# ------------------------------------------------------------------ per-call specs carry timeouts


def _by_prompt(gw: FakeGateway) -> dict[str, GenerationSpec]:
    return {c.spec.prompt_version: c.spec for c in gw.calls}


async def test_diagnosis_specs_carry_stage_timeouts() -> None:
    settings = _settings(
        gemini_timeout_observe=11, gemini_timeout_synthesis=22, gemini_timeout_repair=33
    )
    bad = sample_diagnosis_draft()
    bad.reel_types[0].reason = "내레이션으로 제작 과정을 설명합니다"  # violates face_only
    gw = FakeGateway(responses=[sample_visual(), bad, sample_diagnosis_draft()])
    req = SurveyDiagnosisRequestV1.model_validate(sample_diagnosis_request_dict())
    await DiagnosisService(gw, settings=settings).run(req, fake_image(), request_id="t")
    specs = _by_prompt(gw)
    assert specs[visual_observation.PROMPT_VERSION].timeout_seconds == 11
    assert specs[diagnosis.PROMPT_VERSION].timeout_seconds == 22
    assert specs[repair.PROMPT_VERSION].timeout_seconds == 33


async def test_prescription_specs_carry_stage_timeouts() -> None:
    settings = _settings(
        gemini_timeout_observe=11, gemini_timeout_synthesis=22, gemini_timeout_repair=33
    )
    bad = sample_prescription_draft()
    bad.next_actions[0].title = "..."
    gw = FakeGateway(responses=[sample_insight(), bad, sample_prescription_draft()])
    req = PrescriptionRequestV1.model_validate(sample_prescription_request_dict())
    await PrescriptionService(gw, settings=settings).run(
        req, [fake_image(), fake_image(), fake_image()], request_id="t"
    )
    specs = _by_prompt(gw)
    assert specs[insight_observation.PROMPT_VERSION].timeout_seconds == 11
    assert specs[prescription.PROMPT_VERSION].timeout_seconds == 22
    assert specs[repair.PROMPT_VERSION].timeout_seconds == 33


# ------------------------------------------------------------------ overall deadline


@dataclass(slots=True)
class SlowGateway:
    """Every call sleeps `delay` seconds, then answers like FakeGateway."""

    delay: float
    inner: FakeGateway
    started: list[str] = field(default_factory=list)

    async def generate_structured(
        self,
        *,
        spec: GenerationSpec,
        system_instruction: str,
        user_text: str,
        images: list[ImagePart],
        schema: type[Any],
    ) -> StructuredResult[Any]:
        self.started.append(spec.prompt_version)
        await asyncio.sleep(self.delay)
        return await self.inner.generate_structured(
            spec=spec,
            system_instruction=system_instruction,
            user_text=user_text,
            images=images,
            schema=schema,
        )


async def test_overall_deadline_cuts_diagnosis_and_maps_to_model_timeout() -> None:
    settings = _settings(sosu_request_deadline_seconds=0.15)
    gw = SlowGateway(
        delay=0.2, inner=FakeGateway(responses=[sample_visual(), sample_diagnosis_draft()])
    )
    req = SurveyDiagnosisRequestV1.model_validate(sample_diagnosis_request_dict())
    with pytest.raises(SosuError) as exc:
        await DiagnosisService(gw, settings=settings).run(req, fake_image(), request_id="t")
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    assert exc.value.retryable is True
    assert exc.value.details == [{"deadline_seconds": 0.15}]
    # Deadline fired during the first stage; the synthesis call was never started.
    assert gw.started == [visual_observation.PROMPT_VERSION]


async def test_overall_deadline_cuts_prescription() -> None:
    settings = _settings(sosu_request_deadline_seconds=0.15)
    gw = SlowGateway(
        delay=0.2, inner=FakeGateway(responses=[sample_insight(), sample_prescription_draft()])
    )
    req = PrescriptionRequestV1.model_validate(sample_prescription_request_dict())
    with pytest.raises(SosuError) as exc:
        await PrescriptionService(gw, settings=settings).run(
            req, [fake_image()] * 3, request_id="t"
        )
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    assert gw.started == [insight_observation.PROMPT_VERSION]


async def test_fast_pipeline_is_not_affected_by_deadline() -> None:
    settings = _settings(sosu_request_deadline_seconds=5)
    gw = SlowGateway(
        delay=0.01, inner=FakeGateway(responses=[sample_visual(), sample_diagnosis_draft()])
    )
    req = SurveyDiagnosisRequestV1.model_validate(sample_diagnosis_request_dict())
    report = await DiagnosisService(gw, settings=settings).run(req, fake_image(), request_id="t")
    assert report.schema_version == "diagnosis.v1"
    assert len(gw.started) == 2


async def test_with_deadline_passes_through_inner_sosu_errors() -> None:
    async def boom() -> None:
        raise SosuError(ErrorCode.MODEL_PROVIDER_ERROR, "x")

    with pytest.raises(SosuError) as exc:
        await with_deadline(boom(), seconds=1, request_id="t")
    assert exc.value.code is ErrorCode.MODEL_PROVIDER_ERROR


async def test_with_deadline_returns_value_when_in_time() -> None:
    async def ok() -> StructuredResult[Any]:
        return StructuredResult(value=sample_visual(), usage=UsageRecord())

    result = await with_deadline(ok(), seconds=1, request_id="t")
    assert result.value == sample_visual()
