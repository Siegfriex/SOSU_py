"""Workflow B — Reel URL + 3 Insight screenshots → PrescriptionReportV1 (public contract)."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

INSIGHT_IMAGE_COUNT = 3

_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}
# v1: individual Reel URLs only (/reel/<shortcode> or /reels/<shortcode>). /p/ posts rejected.
_REEL_PATH = re.compile(r"^/(reel|reels)/[A-Za-z0-9_-]+/?$")


def is_valid_instagram_reel_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.hostname not in _INSTAGRAM_HOSTS:
        return False
    return bool(_REEL_PATH.match(parsed.path))


class PrescriptionRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    locale: str = Field(default="ko-KR", max_length=16)
    instagram_url: str = Field(
        max_length=512,
        description=(
            "Individual Instagram Reel URL (https://www.instagram.com/reel/<shortcode>/). "
            "Contextual identifier only — never crawled in v1. /p/ post URLs are rejected."
        ),
    )

    @field_validator("instagram_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.strip()
        if not is_valid_instagram_reel_url(v):
            raise ValueError("INVALID_INSTAGRAM_URL")
        return v


class PrescriptionBody(BaseModel):
    summary: str = Field(description="처방 요약 한두 문장.")
    diagnosis: str = Field(
        description="스크린샷에서 관찰된 지표 근거의 진단. 읽을 수 없는 값은 추정하지 않음."
    )


class NextActionItem(BaseModel):
    order: Literal[1, 2, 3, 4]
    title: str = Field(description="다음 액션 제목.")
    description: str = Field(description="구체적인 실행 방법.")


class PrescriptionToneSection(BaseModel):
    keywords: list[str] = Field(description="권장 톤 키워드 3~5개.")
    description: str = Field(description="다음 릴스에서 유지/변경할 톤 설명.")


class PrescriptionReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["prescription.v1"] = "prescription.v1"
    prescription: PrescriptionBody
    next_actions: list[NextActionItem] = Field(min_length=4, max_length=4)
    tone: PrescriptionToneSection
