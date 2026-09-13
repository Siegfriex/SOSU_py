"""Semantic validation of Gemini drafts (SSOT §14). Schema-valid is not the same as usable."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.evidence import CreatorConstraint
from app.gemini.schemas import DiagnosisDraftV1, PrescriptionDraftV1


class ValidationOutcome(StrEnum):
    PASS = "PASS"
    REPAIRABLE = "REPAIRABLE"
    FATAL = "FATAL"


@dataclass(slots=True)
class ValidationReport:
    outcome: ValidationOutcome
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.outcome is ValidationOutcome.PASS


# ----------------------------------------------------------------- placeholder detection

_PLACEHOLDER_EXACT = frozenset(
    {"...", "…", "n/a", "na", "tbd", "todo", "placeholder", "미정", "없음", "-", "lorem ipsum"}
)
_PLACEHOLDER_SUBSTR = ("lorem ipsum", "placeholder", "tbd", "n/a")
_ONLY_DOTS = re.compile(r"^[.…\s]+$")


def is_placeholder(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if lowered in _PLACEHOLDER_EXACT or _ONLY_DOTS.match(stripped):
        return True
    return any(token in lowered for token in _PLACEHOLDER_SUBSTR)


# ----------------------------------------------------------------- Q18 keyword detection

FACE_KEYWORDS: tuple[str, ...] = (
    "얼굴",
    "표정",
    "셀피",
    "제작자 등장",
    "제작자가 직접 등장",
    "제작자가 등장",
    "얼굴을 보여",
    "on-camera",
    "on camera",
    "face",
    "selfie",
    "talking head",
)
VOICE_KEYWORDS: tuple[str, ...] = (
    "내레이션",
    "나레이션",
    "보이스오버",
    "보이스 오버",
    "목소리",
    "음성 해설",
    "음성으로 설명",
    "음성 설명",
    "직접 말하",
    "voice-over",
    "voiceover",
    "voice over",
    "narration",
    "narrate",
)

# A keyword followed (within a short window) by one of these markers is a compliant negation:
# "얼굴 노출 없이", "내레이션 대신 자막", "목소리를 쓰지 않고".
_NEGATION_MARKERS: tuple[str, ...] = (
    "없이",
    "대신",
    "하지 않",
    "않고",
    "않는",
    "않습",
    "금지",
    "불필요",
    "불가",
    "제외",
    "없는",
    "없어도",
    "without",
    "instead",
    "no ",
)
_NEGATION_WINDOW = 14


def _is_negated(text: str, start: int, end: int) -> bool:
    window = text[end : end + _NEGATION_WINDOW].lower()
    if any(marker in window for marker in _NEGATION_MARKERS):
        return True
    # English-style prefix negation: "without face", "no narration"
    before = text[max(0, start - 10) : start].lower()
    return any(m in before for m in ("without ", "no ", "not "))


def _pattern(keyword: str) -> re.Pattern[str]:
    escaped = re.escape(keyword.lower())
    # ASCII keywords get word boundaries so "face" does not match "surface"/"interface".
    if keyword.isascii():
        return re.compile(rf"\b{escaped}\b")
    return re.compile(escaped)


def find_violations(text: str, keywords: tuple[str, ...]) -> list[str]:
    """Keywords present in `text` that are not covered by a negation window."""
    lowered = text.lower()
    hits: list[str] = []
    for kw in keywords:
        for match in _pattern(kw).finditer(lowered):
            if not _is_negated(text, match.start(), match.end()):
                hits.append(kw)
                break
    return hits


# ----------------------------------------------------------------- helpers


def _check_text(errors: list[str], path: str, value: str) -> None:
    if is_placeholder(value):
        errors.append(f"{path}: 비어 있거나 placeholder입니다.")


def _check_list(errors: list[str], path: str, values: list[str]) -> None:
    if not values:
        errors.append(f"{path}: 비어 있습니다.")
    for i, v in enumerate(values):
        _check_text(errors, f"{path}[{i}]", v)


def _check_constraint(
    errors: list[str], constraint: CreatorConstraint, texts: list[tuple[str, str]]
) -> None:
    for path, text in texts:
        if not constraint.face_allowed:
            hits = find_violations(text, FACE_KEYWORDS)
            if hits:
                errors.append(
                    f"{path}: Q18 제약 위반 — 얼굴 노출 불가인데 {hits!r} 표현이 있습니다."
                )
        if not constraint.voice_allowed:
            hits = find_violations(text, VOICE_KEYWORDS)
            if hits:
                errors.append(
                    f"{path}: Q18 제약 위반 — 목소리 사용 불가인데 {hits!r} 표현이 있습니다."
                )


def _finalize(errors: list[str], total_text_fields: int) -> ValidationReport:
    if not errors:
        return ValidationReport(ValidationOutcome.PASS)
    placeholder_errors = sum(1 for e in errors if "placeholder" in e)
    # Structurally unusable: (almost) every text field is a placeholder → not worth a repair call.
    if total_text_fields and placeholder_errors >= max(3, int(total_text_fields * 0.8)):
        return ValidationReport(ValidationOutcome.FATAL, errors)
    return ValidationReport(ValidationOutcome.REPAIRABLE, errors)


# ----------------------------------------------------------------- public


def validate_diagnosis(draft: DiagnosisDraftV1, constraint: CreatorConstraint) -> ValidationReport:
    errors: list[str] = []
    texts: list[tuple[str, str]] = []

    for path, value in (
        ("brand.name", draft.brand.name),
        ("brand.material", draft.brand.material),
        ("brand.product", draft.brand.product),
        ("positioning.summary", draft.positioning.summary),
        ("positioning.rationale", draft.positioning.rationale),
        ("target.summary", draft.target.summary),
        ("target.description", draft.target.description),
        ("tone.description", draft.tone.description),
        ("fonts.title", draft.fonts.title),
        ("fonts.subtitle", draft.fonts.subtitle),
        ("fonts.reason", draft.fonts.reason),
    ):
        _check_text(errors, path, value)
        texts.append((path, value))

    _check_list(errors, "brand.keywords", draft.brand.keywords)
    _check_list(errors, "tone.keywords", draft.tone.keywords)

    if not draft.strengths:
        errors.append("strengths: 비어 있습니다.")
    for i, s in enumerate(draft.strengths):
        _check_text(errors, f"strengths[{i}].title", s.title)
        _check_text(errors, f"strengths[{i}].description", s.description)
        texts.append((f"strengths[{i}].description", s.description))

    ranks = sorted(p.rank for p in draft.priorities)
    if ranks != [1, 2, 3]:
        errors.append(f"priorities: rank는 정확히 1,2,3이어야 합니다 (현재 {ranks}).")
    constraint_texts: list[tuple[str, str]] = []
    for i, p in enumerate(draft.priorities):
        _check_text(errors, f"priorities[{i}].title", p.title)
        _check_text(errors, f"priorities[{i}].description", p.description)
        constraint_texts.append((f"priorities[{i}]", f"{p.title} {p.description}"))

    for i, r in enumerate(draft.reel_types):
        _check_text(errors, f"reel_types[{i}].name", r.name)
        _check_text(errors, f"reel_types[{i}].reason", r.reason)
        constraint_texts.append((f"reel_types[{i}]", f"{r.name} {r.reason}"))

    for slot in ("hook_0_3", "body_3_10", "body_10_20", "close_20_27", "cta_27_30"):
        value = getattr(draft.structure, slot)
        _check_text(errors, f"structure.{slot}", value)
        constraint_texts.append((f"structure.{slot}", value))

    _check_list(errors, "final_guidance", draft.final_guidance)
    for i, g in enumerate(draft.final_guidance):
        constraint_texts.append((f"final_guidance[{i}]", g))

    _check_constraint(errors, constraint, constraint_texts)

    total = len(texts) + len(constraint_texts) + 2
    return _finalize(errors, total)


def validate_prescription(draft: PrescriptionDraftV1) -> ValidationReport:
    errors: list[str] = []
    _check_text(errors, "prescription.summary", draft.prescription.summary)
    _check_text(errors, "prescription.diagnosis", draft.prescription.diagnosis)

    orders = sorted(a.order for a in draft.next_actions)
    if orders != [1, 2, 3, 4]:
        errors.append(f"next_actions: order는 정확히 1,2,3,4이어야 합니다 (현재 {orders}).")
    for i, a in enumerate(draft.next_actions):
        _check_text(errors, f"next_actions[{i}].title", a.title)
        _check_text(errors, f"next_actions[{i}].description", a.description)

    _check_list(errors, "tone.keywords", draft.tone.keywords)
    _check_text(errors, "tone.description", draft.tone.description)

    return _finalize(errors, 2 + len(draft.next_actions) * 2 + 2)
