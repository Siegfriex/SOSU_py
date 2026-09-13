"""Input sufficiency rule (section 20). Partial completion is allowed."""

from __future__ import annotations

from app.contracts.envelope import ErrorCode
from app.domain.errors import SosuError
from app.domain.evidence import DeclaredEvidenceV1


def ensure_sufficient_input(declared: DeclaredEvidenceV1, *, has_image: bool) -> None:
    """Reject only when there is no meaningful survey answer AND no product image."""
    if not declared.has_meaningful_answer and not has_image:
        raise SosuError(
            ErrorCode.INSUFFICIENT_INPUT,
            "문진 답변이 하나도 없고 제품 이미지도 없습니다. "
            "답변 또는 이미지 중 하나는 필요합니다.",
            details=[{"reason": "no_answers_and_no_image"}],
        )
