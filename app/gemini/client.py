"""google-genai backed GeminiGateway. The only module that imports the vendor SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, ThinkingLevel
from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.gemini.gateway import (
    GenerationSpec,
    ImagePart,
    StructuredResult,
    UsageRecord,
)
from app.gemini.schemas import gemini_json_schema

log = logging.getLogger("sosu.gemini")

_THINKING: dict[ThinkingLevel, genai_types.ThinkingLevel] = {
    "minimal": genai_types.ThinkingLevel.MINIMAL,
    "low": genai_types.ThinkingLevel.LOW,
    "medium": genai_types.ThinkingLevel.MEDIUM,
    "high": genai_types.ThinkingLevel.HIGH,
}

_TRANSIENT_HTTP = frozenset({429, 500, 503})
_CONTENT_FINISH_REASONS = frozenset(
    {
        "MAX_TOKENS",
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "IMAGE_SAFETY",
        "LANGUAGE",
        "OTHER",
    }
)


class _Transient(Exception):
    """Internal marker: provider error worth one retry."""

    def __init__(self, code: int | None) -> None:
        super().__init__(f"transient provider error {code}")
        self.code = code


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, _Transient)


class GoogleGenAIGateway:
    def __init__(self, settings: Settings, *, client: genai.Client | None = None) -> None:
        self._settings = settings
        self._client = client or genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    # -------------------------------------------------------------- public

    async def generate_structured[T: BaseModel](
        self,
        *,
        spec: GenerationSpec,
        system_instruction: str,
        user_text: str,
        images: list[ImagePart],
        schema: type[T],
    ) -> StructuredResult[T]:
        contents: list[Any] = [user_text]
        for image in images:
            contents.append(genai_types.Part.from_bytes(data=image.data, mime_type=image.mime_type))

        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_json_schema=gemini_json_schema(schema),
            thinking_config=genai_types.ThinkingConfig(thinking_level=_THINKING[spec.thinking]),
            max_output_tokens=spec.max_output_tokens,
            temperature=spec.temperature,
            http_options=genai_types.HttpOptions(timeout=int(spec.timeout_seconds * 1000)),
        )

        started = time.perf_counter()
        response = await self._call_with_retry(spec, contents, config)
        latency_ms = int((time.perf_counter() - started) * 1000)

        usage = _usage_from(response)
        text = _extract_text(response)
        try:
            value = schema.model_validate_json(text)
        except ValidationError as exc:
            locs = [".".join(str(p) for p in e["loc"]) for e in exc.errors()[:5]]
            log.warning(
                "gemini schema mismatch prompt=%s model=%s locs=%s",
                spec.prompt_version,
                spec.model,
                locs,
            )
            raise SosuError(
                ErrorCode.MODEL_SCHEMA_ERROR,
                "Model output did not match the expected schema.",
                details=[{"schema": schema.__name__, "locations": locs}],
            ) from None
        except ValueError:
            raise SosuError(
                ErrorCode.MODEL_SCHEMA_ERROR,
                "Model output was not valid JSON.",
                details=[{"schema": schema.__name__}],
            ) from None

        log.info(
            "gemini call prompt=%s model=%s thinking=%s latency_ms=%d "
            "tokens prompt=%s output=%s thoughts=%s total=%s",
            spec.prompt_version,
            spec.model,
            spec.thinking,
            latency_ms,
            usage.prompt_tokens,
            usage.output_tokens,
            usage.thoughts_tokens,
            usage.total_tokens,
        )
        return StructuredResult(value=value, usage=usage, raw_json=text)

    # -------------------------------------------------------------- internals

    async def _call_with_retry(
        self, spec: GenerationSpec, contents: list[Any], config: genai_types.GenerateContentConfig
    ) -> genai_types.GenerateContentResponse:
        retrying = AsyncRetrying(
            retry=retry_if_exception(_is_transient),
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=2.0),
            reraise=False,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    return await self._call_once(spec, contents, config)
        except RetryError as exc:
            last = exc.last_attempt.exception()
            code = last.code if isinstance(last, _Transient) else None
            log.warning(
                "gemini provider error (after retry) prompt=%s status=%s", spec.prompt_version, code
            )
            raise SosuError(
                ErrorCode.MODEL_PROVIDER_ERROR,
                "Model provider is temporarily unavailable.",
                details=[{"status": code}],
            ) from None
        raise SosuError(ErrorCode.INTERNAL_ERROR, "Unreachable retry state.")  # pragma: no cover

    async def _call_once(
        self, spec: GenerationSpec, contents: list[Any], config: genai_types.GenerateContentConfig
    ) -> genai_types.GenerateContentResponse:
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=spec.model, contents=contents, config=config
                ),
                timeout=spec.timeout_seconds,
            )
        except (TimeoutError, httpx.TimeoutException):
            log.warning("gemini timeout prompt=%s model=%s", spec.prompt_version, spec.model)
            raise SosuError(
                ErrorCode.MODEL_TIMEOUT, "Model request timed out.", details=[]
            ) from None
        except genai_errors.APIError as exc:
            status = getattr(exc, "code", None)
            if status in _TRANSIENT_HTTP:
                raise _Transient(status) from None
            log.warning("gemini provider error prompt=%s status=%s", spec.prompt_version, status)
            raise SosuError(
                ErrorCode.MODEL_PROVIDER_ERROR,
                "Model provider rejected the request.",
                details=[{"status": status}],
                retryable=False,
            ) from None
        except SosuError:
            raise
        except Exception:  # SDK surprises: never leak text
            log.exception("gemini unexpected failure prompt=%s", spec.prompt_version)
            raise SosuError(ErrorCode.MODEL_PROVIDER_ERROR, "Model provider call failed.") from None

        _check_candidates(response)
        return response


def _check_candidates(response: genai_types.GenerateContentResponse) -> None:
    feedback = getattr(response, "prompt_feedback", None)
    block = getattr(feedback, "block_reason", None) if feedback else None
    if block:
        raise SosuError(
            ErrorCode.MODEL_CONTENT_ERROR,
            "Model declined to generate content.",
            details=[{"block_reason": str(getattr(block, "name", block))}],
        )
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise SosuError(ErrorCode.MODEL_CONTENT_ERROR, "Model returned no candidates.", details=[])
    reason = getattr(candidates[0], "finish_reason", None)
    reason_name = str(getattr(reason, "name", reason or "")) if reason is not None else ""
    if reason_name in _CONTENT_FINISH_REASONS:
        raise SosuError(
            ErrorCode.MODEL_CONTENT_ERROR,
            "Model output was cut off or filtered.",
            details=[{"finish_reason": reason_name}],
        )


def _extract_text(response: genai_types.GenerateContentResponse) -> str:
    text: str | None = None
    try:
        text = response.text
    except Exception:  # SDK raises on mixed/empty parts
        text = None
    if not text:
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            text = json.dumps(parsed, ensure_ascii=False)
    if not text:
        raise SosuError(ErrorCode.MODEL_CONTENT_ERROR, "Model returned empty output.", details=[])
    return text


def _usage_from(response: genai_types.GenerateContentResponse) -> UsageRecord:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return UsageRecord()
    return UsageRecord(
        prompt_tokens=getattr(meta, "prompt_token_count", None),
        output_tokens=getattr(meta, "candidates_token_count", None),
        thoughts_tokens=getattr(meta, "thoughts_token_count", None),
        total_tokens=getattr(meta, "total_token_count", None),
    )
