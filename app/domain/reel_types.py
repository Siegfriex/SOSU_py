"""Guidebook reel types (가이드북 2차 pp.11-14, rules GB-TYPE-* / GB-COMBO-*).

A diagnosis recommends one type per axis — order (A/B), sound (C/D), caption (E/F) — and the
three together form the combination (e.g. B+D+F). The model only picks the letter; the public
`ReelTypeItem.name` is always the fixed label below, so names can never drift.
"""

from __future__ import annotations

import re
from typing import Literal

ReelTypeCode = Literal["A", "B", "C", "D", "E", "F"]

# Titles verbatim from the guidebook (2-1 ~ 2-3).
REEL_TYPE_LABELS: dict[str, str] = {
    "A": "제작 과정을 순서대로",
    "B": "완성된 제품을 먼저",
    "C": "사운드가 강할 경우",
    "D": "사운드가 약할 경우",
    "E": "자막이나 나레이션이 없는 경우",
    "F": "자막이나 나레이션이 있는 경우",
}

# (axis name shown to users, allowed codes) in display order.
REEL_AXES: tuple[tuple[str, tuple[str, str]], ...] = (
    ("순서", ("A", "B")),
    ("사운드", ("C", "D")),
    ("자막", ("E", "F")),
)

_NAME_RE = re.compile(r"^유형 ([A-F]) · ")


# Q18 voice not allowed: the caption axis is implemented with on-screen text only, so the label
# drops 나레이션 (a voice-free creator must never see a voice-based suggestion).
VOICE_FREE_LABELS: dict[str, str] = {
    "E": "자막이 없는 경우",
    "F": "자막이 있는 경우",
}


def reel_type_name(code: str, *, voice_allowed: bool = True) -> str:
    label = (
        REEL_TYPE_LABELS[code]
        if voice_allowed
        else VOICE_FREE_LABELS.get(code, REEL_TYPE_LABELS[code])
    )
    return f"유형 {code} · {label}"


def code_of_name(name: str) -> str | None:
    """Letter of a canonical name (`유형 B · …`), else None (pre-guidebook free-text names)."""
    m = _NAME_RE.match(name)
    return m.group(1) if m else None


def axis_errors(codes: list[str]) -> list[str]:
    """Exactly one code per axis; returns Korean validator messages (empty when valid)."""
    errors: list[str] = []
    for axis, allowed in REEL_AXES:
        picked = [c for c in codes if c in allowed]
        if len(picked) != 1:
            errors.append(
                f"reel_types: {axis} 축({'/'.join(allowed)})에서 정확히 하나를 골라야 합니다 "
                f"(현재 {picked or '없음'}). code를 바꾸면 그 항목의 reason도 새 유형에 맞게 "
                "다시 쓰세요."
            )
    return errors


def combination(codes: list[str]) -> str:
    """'B+D+F' in axis order."""
    return "+".join(sorted(codes))
