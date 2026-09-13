"""GeminiGateway abstraction. Vendor SDK calls live only in app/gemini/*.

Domain/service code depends on `GeminiGateway` (Protocol) and never imports google.genai.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.config import ThinkingLevel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ImagePart:
    data: bytes
    mime_type: str = "image/jpeg"


@dataclass(frozen=True, slots=True)
class GenerationSpec:
    """Per-call config resolved from Settings by the caller (no hardcoded models/keys)."""

    model: str
    thinking: ThinkingLevel
    max_output_tokens: int
    prompt_version: str
    timeout_seconds: float = 90.0
    temperature: float | None = None


@dataclass(slots=True)
class UsageRecord:
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thoughts_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(slots=True)
class StructuredResult[T: BaseModel]:
    value: T
    usage: UsageRecord = field(default_factory=UsageRecord)
    raw_json: str | None = None


class GeminiGateway(Protocol):
    async def generate_structured(
        self,
        *,
        spec: GenerationSpec,
        system_instruction: str,
        user_text: str,
        images: list[ImagePart],
        schema: type[T],
    ) -> StructuredResult[T]:
        """Structured JSON generation. Raises SosuError(MODEL_*) — never raw SDK exceptions."""
        ...
