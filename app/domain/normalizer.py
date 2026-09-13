"""Deterministic InputNormalizer: SurveyAnswersV1 → DeclaredEvidenceV1.

Allowed on natural language: unicode NFC, CRLF→LF, strip, collapse excessive blank lines,
empty → None, safe max length. Never paraphrase, summarize, or translate.
"""

from __future__ import annotations

import re
import unicodedata

from app.contracts.diagnosis import SurveyAnswersV1
from app.domain.evidence import CreatorConstraint, DeclaredEvidenceV1

SAFE_MAX_TEXT_LEN = 2000

TEXT_FIELDS: tuple[str, ...] = (
    "q1_brand_name",
    "q2_product_category",
    "q3_hero_product",
    "q4_materials",
    "q5_material_reason",
    "q7_differentiation",
    "q8_target_customer",
    "q12_avoidance",
    "q13_motif",
    "q14_primary_message",
    "q15_interesting_process",
    "q20_must_show",
)

LIST_FIELDS: tuple[str, ...] = (
    "q6_product_appeals",
    "q9_purchase_motives",
    "q10_desired_emotions",
    "q11_brand_attributes",
    "q16_pain_points",
    "q17_current_formats",
)

_BLANK_LINES = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+\n")


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFC", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_WS.sub("\n", text)
    text = _BLANK_LINES.sub("\n\n", text)
    text = text.strip()
    if not text:
        return None
    if len(text) > SAFE_MAX_TEXT_LEN:
        text = text[:SAFE_MAX_TEXT_LEN].rstrip()
    return text


def _dedupe[E](items: list[E]) -> list[E]:
    seen: set[object] = set()
    out: list[E] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def normalize_survey(answers: SurveyAnswersV1) -> DeclaredEvidenceV1:
    data: dict[str, object] = {}
    answered: list[str] = []

    for name in TEXT_FIELDS:
        norm = normalize_text(getattr(answers, name))
        data[name] = norm
        if norm is not None:
            answered.append(name.split("_", 1)[0])

    for name in LIST_FIELDS:
        items = _dedupe(list(getattr(answers, name)))
        data[name] = items
        if items:
            answered.append(name.split("_", 1)[0])

    if answers.q18_disclosure is not None:
        answered.append("q18")
    data["q18_disclosure"] = answers.q18_disclosure
    data["creator_constraint"] = CreatorConstraint.from_disclosure(answers.q18_disclosure)
    data["answered_question_ids"] = answered
    return DeclaredEvidenceV1.model_validate(data)
