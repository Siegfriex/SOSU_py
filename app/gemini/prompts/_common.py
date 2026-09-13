# ruff: noqa: E501  -- prompt prose lines are intentionally long
"""Shared prompt helpers."""

from __future__ import annotations

import json
from typing import Any

from app.domain.evidence import CreatorConstraint, InferencePolicyV1


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def output_language(locale: str) -> str:
    if locale.lower().startswith("ko"):
        return "한국어"
    if locale.lower().startswith("en"):
        return "English"
    if locale.lower().startswith("ja"):
        return "日本語"
    return f"locale '{locale}'에 맞는 언어"


def constraint_sentences(constraint: CreatorConstraint) -> str:
    face = (
        "제작자의 얼굴 노출 가능."
        if constraint.face_allowed
        else "제작자의 얼굴 노출 불가. 얼굴/표정/제작자 등장을 전제로 한 장면·훅·릴스 유형을 제안하지 말 것."
    )
    voice = (
        "제작자의 목소리 사용 가능."
        if constraint.voice_allowed
        else (
            "제작자의 목소리 사용 불가. 내레이션/보이스오버/음성 설명을 전제로 한 제안 금지. "
            "설명이 필요하면 자막·화면 텍스트·BGM으로 대체할 것."
        )
    )
    source = constraint.source.value if constraint.source else "미응답(제약 없음으로 간주)"
    return f"- Q18 응답: {source}\n- {face}\n- {voice}"


def policy_table(policy: InferencePolicyV1) -> str:
    lines = ["| section | primary | supporting | constraint |", "|---|---|---|---|"]
    for section, routing in policy.routing.items():
        lines.append(
            f"| {section} | {', '.join(routing.primary)} | "
            f"{', '.join(routing.supporting) or '-'} | {', '.join(routing.constraint) or '-'} |"
        )
    return "\n".join(lines)
