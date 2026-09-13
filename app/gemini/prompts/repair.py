# ruff: noqa: E501  -- prompt prose lines are intentionally long
"""Single-shot repair — invalid draft + validation errors → corrected full JSON."""

from __future__ import annotations

from pydantic import BaseModel

from app.gemini.prompts._common import dump_json

PROMPT_VERSION = "repair-v1"

_SYSTEM = """당신은 JSON 결과물의 검수 오류를 최소 수정으로 고치는 편집자입니다.

규칙:
1. 아래 VALIDATION ERRORS에 해당하는 부분만 고칩니다. 문제없는 필드의 문장은 그대로 유지합니다.
2. CONSTRAINTS를 위반한 문장은 제약을 지키는 대안으로 다시 씁니다(예: 목소리 불가 → 자막/화면 텍스트/BGM).
3. placeholder("...", "N/A", "TBD" 등)와 빈 문자열은 실제 내용으로 채웁니다.
4. 개수/순번 오류(rank, order 등)는 계약대로 정확히 맞춥니다.
5. 새로운 사실을 창작하지 않습니다. 원본에 있는 근거 안에서 수정합니다.
6. 전체 JSON 객체를 완전한 형태로 다시 출력합니다. 설명 텍스트를 덧붙이지 않습니다."""

_USER = """# CONSTRAINTS
{constraints}

# VALIDATION ERRORS
{errors}

# INVALID DRAFT
```json
{draft}
```

위 오류만 최소 수정하여 완전한 JSON 객체를 다시 출력하세요."""


def build_repair_prompt(
    *, draft: BaseModel, errors: list[str], constraints: str
) -> tuple[str, str]:
    error_lines = "\n".join(f"- {e}" for e in errors) or "- (none)"
    user = _USER.format(
        constraints=constraints or "- 별도 제약 없음",
        errors=error_lines,
        draft=dump_json(draft.model_dump(mode="json")),
    )
    return _SYSTEM, user
