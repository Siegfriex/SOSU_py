"""M — repair runs at most once."""

from __future__ import annotations

import pytest
from app.contracts.enums import CreatorDisclosure
from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.domain.evidence import CreatorConstraint
from app.domain.validator import validate_diagnosis
from app.gemini.gateway import GenerationSpec
from app.gemini.prompts import repair as repair_prompt
from app.gemini.schemas import DiagnosisDraftV1
from app.services.repair import run_with_repair

from tests.fakes import FakeGateway, diagnosis_draft_dict, sample_diagnosis_draft

REPAIR_SPEC = GenerationSpec(
    model="test-model",
    thinking="low",
    max_output_tokens=4096,
    prompt_version=repair_prompt.PROMPT_VERSION,
)
FACE_ONLY = CreatorConstraint.from_disclosure(CreatorDisclosure.FACE_ONLY)


def _violating() -> DiagnosisDraftV1:
    d = diagnosis_draft_dict()
    d["reel_types"][0]["reason"] = "제작자가 내레이션으로 과정을 설명"
    return sample_diagnosis_draft(**d)


def _run(gateway: FakeGateway, draft: DiagnosisDraftV1):
    return run_with_repair(
        gateway=gateway,
        spec_repair=REPAIR_SPEC,
        draft=draft,
        validate=lambda d: validate_diagnosis(d, FACE_ONLY),
        build_repair_prompt=lambda d, errors: repair_prompt.build_repair_prompt(
            draft=d, errors=errors, constraints="- 목소리 사용 불가"
        ),
        schema=DiagnosisDraftV1,
        request_id="req-test",
    )


async def test_pass_needs_no_gateway_call():
    gw = FakeGateway([])
    out = await _run(gw, sample_diagnosis_draft())
    assert out.brand.name == "모노유리"
    assert gw.calls == []


async def test_repair_once_then_pass():
    gw = FakeGateway([sample_diagnosis_draft()])
    out = await _run(gw, _violating())
    assert len(gw.calls) == 1
    call = gw.calls[0]
    assert call.spec.prompt_version == "repair-v1"
    assert call.schema is DiagnosisDraftV1
    assert call.image_count == 0
    assert "VALIDATION ERRORS" in call.user_text and "Q18" in call.user_text
    assert "내레이션" in call.user_text  # the invalid draft is passed back verbatim
    assert out.reel_types[0].reason == sample_diagnosis_draft().reel_types[0].reason


async def test_repair_still_invalid_raises_and_never_calls_third_time():
    gw = FakeGateway([_violating(), sample_diagnosis_draft()])  # 2nd clean one must never be used
    with pytest.raises(SosuError) as exc:
        await _run(gw, _violating())
    assert exc.value.code is ErrorCode.REPAIR_FAILED
    assert exc.value.retryable is True
    assert len(gw.calls) == 1
    assert len(gw.responses) == 1  # the extra scripted response was never consumed


async def test_repair_gateway_error_propagates():
    gw = FakeGateway([SosuError(ErrorCode.MODEL_TIMEOUT, "timeout")])
    with pytest.raises(SosuError) as exc:
        await _run(gw, _violating())
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    assert len(gw.calls) == 1
