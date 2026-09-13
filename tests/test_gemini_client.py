"""GoogleGenAIGateway: schema sanitizing + error mapping. No network."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from app.config import Settings
from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.domain.evidence import VisualObservationV1
from app.gemini.client import GoogleGenAIGateway
from app.gemini.gateway import GenerationSpec
from app.gemini.schemas import DiagnosisDraftV1, PrescriptionDraftV1, gemini_json_schema
from google.genai import errors as genai_errors

from tests.fakes import sample_visual

SPEC = GenerationSpec(
    model="m", thinking="low", max_output_tokens=256, prompt_version="visual-observation-v1"
)


def _walk(node: Any, seen: list[tuple[str, Any]], path: str = "") -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            seen.append((path + "/" + k, v))
            _walk(v, seen, path + "/" + k)
    elif isinstance(node, list):
        for item in node:
            _walk(item, seen, path)


# ----------------------------------------------------------------------------- sanitizer


@pytest.mark.parametrize("model", [DiagnosisDraftV1, PrescriptionDraftV1, VisualObservationV1])
def test_sanitized_schema_has_no_title_default_additional_properties_or_const(model):
    schema = gemini_json_schema(model)
    seen: list[tuple[str, Any]] = []
    _walk(schema, seen)
    for path, _value in seen:
        key = path.rsplit("/", 1)[-1]
        parent = path.rsplit("/", 2)[-2] if path.count("/") >= 2 else ""
        if parent in ("properties", "$defs"):
            continue  # a *property* may legitimately be named "title"
        assert key not in ("title", "default", "additionalProperties", "const"), path
    json.dumps(schema)  # serializable


def test_sanitizer_keeps_counts_bounds_and_refs():
    schema = gemini_json_schema(DiagnosisDraftV1)
    props = schema["properties"]
    assert props["priorities"]["minItems"] == 3 and props["priorities"]["maxItems"] == 3
    assert props["reel_types"]["minItems"] == 3 and props["reel_types"]["maxItems"] == 3
    assert props["priorities"]["items"]["$ref"] == "#/$defs/PriorityDraft"
    rank = schema["$defs"]["PriorityDraft"]["properties"]["rank"]
    assert rank["minimum"] == 1 and rank["maximum"] == 3
    assert "description" in props["priorities"]
    # Property literally named "title" survives inside StrengthItem
    assert "title" in schema["$defs"]["StrengthItem"]["properties"]


def test_sanitizer_rewrites_const_as_enum():
    from typing import Literal

    from pydantic import BaseModel

    class M(BaseModel):
        kind: Literal["x"]

    schema = gemini_json_schema(M)
    assert schema["properties"]["kind"]["enum"] == ["x"]
    assert "const" not in schema["properties"]["kind"]


# ----------------------------------------------------------------------------- gateway


class _FakeAio:
    def __init__(self, behaviour):
        self._behaviour = behaviour
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        result = self._behaviour(len(self.calls))
        if isinstance(result, BaseException):
            raise result
        return result


def _gateway(behaviour, *, timeout: float = 5.0) -> tuple[GoogleGenAIGateway, _FakeAio]:
    aio = _FakeAio(behaviour)
    client = SimpleNamespace(aio=SimpleNamespace(models=aio))
    settings = Settings(gemini_api_key="k")  # type: ignore[arg-type]
    return GoogleGenAIGateway(settings, client=client), aio  # type: ignore[arg-type]


def _response(text: str | None, *, finish: str = "STOP", usage: bool = True, candidates=True):
    cand = SimpleNamespace(finish_reason=SimpleNamespace(name=finish), content=None)
    meta = (
        SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=20,
            thoughts_token_count=5,
            total_token_count=35,
        )
        if usage
        else None
    )
    return SimpleNamespace(
        text=text,
        parsed=None,
        candidates=[cand] if candidates else [],
        prompt_feedback=None,
        usage_metadata=meta,
    )


async def _call(gw: GoogleGenAIGateway):
    return await gw.generate_structured(
        spec=SPEC,
        system_instruction="sys",
        user_text="user",
        images=[],
        schema=VisualObservationV1,
    )


async def test_success_parses_and_reports_usage():
    payload = sample_visual().model_dump_json()
    gw, aio = _gateway(lambda n: _response(payload))
    result = await _call(gw)
    assert result.value == sample_visual()
    assert result.usage.total_tokens == 35 and result.usage.thoughts_tokens == 5
    cfg = aio.calls[0]["config"]
    assert aio.calls[0]["model"] == "m"
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema["type"] == "object"
    assert cfg.thinking_config.thinking_level.name == "LOW"
    assert cfg.thinking_config.include_thoughts is None
    assert cfg.max_output_tokens == 256
    assert cfg.system_instruction == "sys"
    assert aio.calls[0]["contents"] == ["user"]


async def test_timeout_maps_to_model_timeout():
    gw, aio = _gateway(lambda n: TimeoutError())
    with pytest.raises(SosuError) as exc:
        await _call(gw)
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT
    assert exc.value.retryable is True
    assert len(aio.calls) == 1  # timeouts are not retried by the gateway


async def test_slow_call_is_cut_by_wait_for():
    async def slow(**kwargs):
        await asyncio.sleep(1.0)

    aio = _FakeAio(lambda n: None)
    aio.generate_content = slow  # type: ignore[method-assign]
    client = SimpleNamespace(aio=SimpleNamespace(models=aio))
    settings = Settings(gemini_api_key="k")  # type: ignore[arg-type]
    gw = GoogleGenAIGateway(settings, client=client)  # type: ignore[arg-type]
    with pytest.raises(SosuError) as exc:
        await gw.generate_structured(
            spec=replace(SPEC, timeout_seconds=0.05),
            system_instruction="sys",
            user_text="user",
            images=[],
            schema=VisualObservationV1,
        )
    assert exc.value.code is ErrorCode.MODEL_TIMEOUT


async def test_non_transient_api_error_maps_to_provider_error_without_retry():
    err = genai_errors.APIError(400, {"error": {"message": "secret-detail", "status": "BAD"}})
    gw, aio = _gateway(lambda n: err)
    with pytest.raises(SosuError) as exc:
        await _call(gw)
    assert exc.value.code is ErrorCode.MODEL_PROVIDER_ERROR
    assert "secret-detail" not in exc.value.message
    assert exc.value.details == [{"status": 400}]
    assert len(aio.calls) == 1


async def test_transient_api_error_retries_once_then_fails():
    err = genai_errors.APIError(503, {"error": {"message": "unavailable", "status": "UNAVAILABLE"}})
    gw, aio = _gateway(lambda n: err)
    with pytest.raises(SosuError) as exc:
        await _call(gw)
    assert exc.value.code is ErrorCode.MODEL_PROVIDER_ERROR
    assert exc.value.retryable is True
    assert len(aio.calls) == 2  # exactly one retry


async def test_transient_then_success():
    payload = sample_visual().model_dump_json()
    err = genai_errors.APIError(
        429, {"error": {"message": "slow down", "status": "RESOURCE_EXHAUSTED"}}
    )
    gw, aio = _gateway(lambda n: err if n == 1 else _response(payload))
    result = await _call(gw)
    assert result.value == sample_visual()
    assert len(aio.calls) == 2


async def test_empty_candidates_is_content_error():
    gw, _ = _gateway(lambda n: _response(None, candidates=False))
    with pytest.raises(SosuError) as exc:
        await _call(gw)
    assert exc.value.code is ErrorCode.MODEL_CONTENT_ERROR


@pytest.mark.parametrize("finish", ["SAFETY", "RECITATION", "MAX_TOKENS"])
async def test_bad_finish_reason_is_content_error(finish):
    gw, _ = _gateway(lambda n: _response("{}", finish=finish))
    with pytest.raises(SosuError) as exc:
        await _call(gw)
    assert exc.value.code is ErrorCode.MODEL_CONTENT_ERROR
    assert exc.value.details == [{"finish_reason": finish}]


async def test_invalid_json_is_schema_error():
    gw, _ = _gateway(lambda n: _response("not json at all"))
    with pytest.raises(SosuError) as exc:
        await _call(gw)
    assert exc.value.code is ErrorCode.MODEL_SCHEMA_ERROR


async def test_schema_mismatch_is_schema_error_with_locations():
    gw, _ = _gateway(lambda n: _response(json.dumps({"dominant_visual_traits": "not-a-list"})))
    with pytest.raises(SosuError) as exc:
        await _call(gw)
    assert exc.value.code is ErrorCode.MODEL_SCHEMA_ERROR
    assert exc.value.details[0]["schema"] == "VisualObservationV1"
    assert "dominant_visual_traits" in exc.value.details[0]["locations"]


async def test_unexpected_exception_is_provider_error_without_leak():
    gw, _ = _gateway(lambda n: RuntimeError("stack trace with key AIza-nope"))
    with pytest.raises(SosuError) as exc:
        await _call(gw)
    assert exc.value.code is ErrorCode.MODEL_PROVIDER_ERROR
    assert "AIza" not in exc.value.message and not exc.value.details


async def test_images_become_inline_parts():
    from app.gemini.gateway import ImagePart

    payload = sample_visual().model_dump_json()
    gw, aio = _gateway(lambda n: _response(payload))
    await gw.generate_structured(
        spec=SPEC,
        system_instruction="sys",
        user_text="user",
        images=[ImagePart(data=b"abc", mime_type="image/jpeg")],
        schema=VisualObservationV1,
    )
    contents = aio.calls[0]["contents"]
    assert contents[0] == "user"
    assert contents[1].inline_data.mime_type == "image/jpeg"
    assert contents[1].inline_data.data == b"abc"
