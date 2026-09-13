"""Assemble EvidencePackV1 for diagnosis synthesis and derive internal trace metadata."""

from __future__ import annotations

from typing import TypedDict

from app.domain.evidence import DeclaredEvidenceV1, EvidencePackV1, VisualObservationV1
from app.domain.normalizer import LIST_FIELDS, TEXT_FIELDS
from app.domain.policy import INFERENCE_POLICY_V1

_TEXT_QIDS = frozenset(name.split("_", 1)[0] for name in TEXT_FIELDS)
_CATEGORICAL_QIDS = frozenset(name.split("_", 1)[0] for name in LIST_FIELDS) | {"q18"}


class EvidenceMeta(TypedDict):
    """Internal trace only. Never a user-facing score; no pseudo-probabilities."""

    has_product_image: bool
    answered_fields: int
    categorical_fields: int
    free_text_fields: int


def build_evidence_pack(
    declared: DeclaredEvidenceV1,
    visual: VisualObservationV1 | None,
    *,
    locale: str = "ko-KR",
) -> EvidencePackV1:
    return EvidencePackV1(
        declared=declared,
        visual=visual,
        policy=INFERENCE_POLICY_V1,
        locale=locale,
    )


def evidence_meta(pack: EvidencePackV1) -> EvidenceMeta:
    answered = pack.declared.answered_question_ids
    return EvidenceMeta(
        has_product_image=pack.visual is not None,
        answered_fields=len(answered),
        categorical_fields=sum(1 for q in answered if q in _CATEGORICAL_QIDS),
        free_text_fields=sum(1 for q in answered if q in _TEXT_QIDS),
    )
