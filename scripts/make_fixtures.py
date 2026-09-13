# ruff: noqa: E501
"""Generate contracts/fixtures/* and contracts/README.md from the runtime models.

Every fixture is `model_dump(mode="json")` of a validated Pydantic instance — never hand-written.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.errors import GENERIC_INTERNAL_MESSAGE, envelope_for  # noqa: E402
from app.contracts.catalog import SSOT_CODE_ALIASES, catalog_as_json  # noqa: E402
from app.contracts.diagnosis import DiagnosisReportV1, SurveyDiagnosisRequestV1  # noqa: E402
from app.contracts.envelope import ErrorCode, SuccessEnvelope  # noqa: E402
from app.contracts.prescription import PrescriptionReportV1, PrescriptionRequestV1  # noqa: E402
from app.domain.errors import SosuError  # noqa: E402
from app.images.types import (  # noqa: E402
    ACCEPTED_IMAGE_TYPES,
    INSIGHT_IMAGE_COUNT,
    INSIGHT_IMAGE_MAX_BYTES,
    INSIGHT_IMAGES_MAX_TOTAL_BYTES,
    PRODUCT_IMAGE_MAX_BYTES,
)

FIXTURES_DIR = ROOT / "contracts" / "fixtures"
README_PATH = ROOT / "contracts" / "README.md"

# ------------------------------------------------------------------ request fixtures

DIAGNOSIS_REQUEST: dict[str, Any] = {
    "contract_version": "1.0",
    "locale": "ko-KR",
    "answers": {
        "q1_brand_name": "모노유리",
        "q2_product_category": "유리 비즈로 만드는 키링과 작은 오브제",
        "q3_hero_product": "빛을 받으면 색이 달라 보이는 유리 키링",
        "q4_materials": "체코 유리비즈, 스테인리스",
        "q5_material_reason": "빛에 따라 표정이 달라져서",
        "q6_product_appeals": ["design", "detail", "rarity"],
        "q7_differentiation": "같은 색 조합으로 대량 제작하지 않고 매번 조금씩 다르게 만듭니다.",
        "q8_target_customer": "흔한 캐릭터 제품보다 조금 독특한 소품을 좋아하는 20~30대",
        "q9_purchase_motives": ["aesthetic", "self_expression"],
        "q10_desired_emotions": ["excitement", "specialness"],
        "q11_brand_attributes": ["warmth", "specialness"],
        "q12_avoidance": "너무 유아적이거나 값싸 보이는 느낌",
        "q13_motif": "별빛, 물결",
        "q14_primary_message": "빛을 받았을 때 유리가 반짝이는 것",
        "q15_interesting_process": "색 조합을 고르고 하나씩 연결하는 과정",
        "q16_pain_points": ["low_reach", "ideation"],
        "q17_current_formats": ["finished_product"],
        "q18_disclosure": "face_only",
        "q20_must_show": "포장하기 전에 햇빛에 비춰보는 장면",
    },
}

PRESCRIPTION_REQUEST: dict[str, Any] = {
    "contract_version": "1.0",
    "locale": "ko-KR",
    "instagram_url": "https://www.instagram.com/reel/C0ffeeBeanz/",
}

# ------------------------------------------------------------------ success fixtures
# face_only: 얼굴 노출은 가능하지만 목소리는 사용하지 않음 → 내레이션/보이스오버 없이 자막·BGM 중심.

DIAGNOSIS_REPORT: dict[str, Any] = {
    "schema_version": "diagnosis.v1",
    "brand": {
        "name": "모노유리",
        "material": "체코 유리비즈와 스테인리스",
        "product": "빛에 따라 색이 달라 보이는 유리 키링",
        "keywords": ["빛", "유리 디테일", "개별성", "별빛", "물결"],
    },
    "positioning": {
        "summary": "빛에 따라 표정이 달라지는, 하나뿐인 작은 유리 오브제",
        "rationale": (
            "설문에서 디자인·디테일·희소성을 강점으로 선언했고, 이미지에서는 유리 표면의 반사와 "
            "미세한 비즈 디테일이 가장 강한 시각 신호로 관찰됩니다. 희소성은 이미지만으로 확인되지 "
            "않으므로 '매번 조금씩 다른 색 조합' 제작 과정을 보여줄 때 설득력이 생깁니다."
        ),
    },
    "strengths": [
        {
            "title": "빛에 반응하는 소재감",
            "description": (
                "정지된 완성품보다 움직임 속에서 유리 반사가 드러날 때 차별점이 선명해집니다. "
                "햇빛 아래에서 제품을 천천히 돌리는 장면이 핵심 자산입니다."
            ),
        },
        {
            "title": "하나씩 고르는 색 조합",
            "description": (
                "투명한 비즈와 탁한 비즈를 섞어 매번 다르게 만드는 과정은 '똑같은 것이 없다'는 "
                "희소성을 말이 아닌 장면으로 증명합니다."
            ),
        },
        {
            "title": "손끝 디테일",
            "description": "비즈를 연결하는 손동작 클로즈업은 수공예의 신뢰를 짧은 컷으로 전달합니다.",
        },
    ],
    "target": {
        "summary": "흔한 캐릭터 소품 대신 나만의 작은 오브제를 찾는 20~30대",
        "description": (
            "예뻐서, 그리고 나만의 것을 갖고 싶어서 구매하는 고객입니다. 설렘과 특별함을 느끼고 "
            "싶어 하므로 '세상에 하나뿐인 조합'이라는 메시지가 구매 동기와 직접 맞닿습니다."
        ),
    },
    "tone": {
        "keywords": ["따뜻한", "섬세한", "조용한 특별함", "빛"],
        "description": (
            "자연광 위주의 밝고 부드러운 색감, 느린 속도감, 과장되지 않은 자막. 유아적이거나 "
            "값싸 보이는 인상을 피하기 위해 원색 배경과 빠른 트랜지션은 지양합니다."
        ),
    },
    "fonts": {
        "title": "단정한 산세리프, 중간 이상의 굵기",
        "subtitle": "가독성 높은 산세리프 Regular",
        "reason": (
            "따뜻함과 특별함을 동시에 전달하려면 장식성이 낮고 여백이 살아 있는 서체가 유리합니다. "
            "둥근 손글씨체는 유아적으로 보일 수 있어 피합니다."
        ),
    },
    "priorities": [
        {
            "rank": 1,
            "title": "햇빛을 통과하는 유리",
            "description": "첫 3초 안에 제품을 손으로 움직여 빛 반사와 색 변화를 보여줍니다.",
        },
        {
            "rank": 2,
            "title": "포장 전 햇빛 확인 장면",
            "description": (
                "반드시 보여주고 싶다고 답한 '포장 전에 햇빛에 비춰보는 장면'을 고정 엔딩 컷으로 "
                "사용해 브랜드 시그니처로 만듭니다."
            ),
        },
        {
            "rank": 3,
            "title": "색 조합을 고르는 손",
            "description": "비즈를 고르고 하나씩 꿰는 과정을 짧게 넣어 '매번 다르다'를 증명합니다.",
        },
    ],
    "reel_types": [
        {
            "name": "제작 디테일형",
            "reason": (
                "현재 완성품 위주 콘텐츠에서 보이지 않던 제작 차별점을 보완합니다. 얼굴이 함께 "
                "나와도 되므로 작업하는 모습과 손 클로즈업을 섞어 구성합니다."
            ),
        },
        {
            "name": "빛 변화 무드형",
            "reason": (
                "빛에 따라 달라지는 색이 핵심 메시지이므로 BGM과 자막만으로 구성된 짧은 무드 릴스가 "
                "조회수 문제에 가장 직접적으로 대응합니다."
            ),
        },
        {
            "name": "완성 전후 비교형",
            "reason": (
                "비즈 더미에서 완성 키링까지의 대비는 아이디어 고갈 없이 반복 제작 가능한 포맷입니다."
            ),
        },
    ],
    "structure": {
        "hook_0_3": "햇빛 아래에서 키링을 천천히 돌리며 색이 바뀌는 순간을 클로즈업. 자막: '빛에 따라 달라지는 한 점'",
        "body_3_10": "비즈 트레이에서 색을 고르는 손. 자막으로 '같은 조합은 없어요'.",
        "body_10_20": "하나씩 꿰는 과정 2~3컷, 제작자의 집중한 모습을 짧게 삽입.",
        "close_20_27": "포장 전 햇빛에 비춰보는 시그니처 장면.",
        "cta_27_30": "완성 키링 3종 나열 + 자막 '오늘의 조합은 프로필 링크에서'.",
    },
    "final_guidance": [
        "목소리 없이도 전달되도록 모든 핵심 메시지는 자막으로 넣습니다.",
        "제작 과정 릴스를 주 1회 고정 포맷으로 만들어 아이디어 고갈을 줄입니다.",
        "완성품 사진 릴스는 유지하되, 반드시 빛 반사 컷을 첫 장면으로 배치합니다.",
    ],
}

PRESCRIPTION_REPORT: dict[str, Any] = {
    "schema_version": "prescription.v1",
    "prescription": {
        "summary": "도달은 충분하지만 시청 유지가 초반에 끊기는 릴스입니다. 첫 3초 훅을 재설계하세요.",
        "diagnosis": (
            "스크린샷 1에서 도달 계정 수 대비 팔로우 전환이 낮게 표시되고, 스크린샷 2의 시청 유지 "
            "그래프는 3초 부근에서 가파르게 하락합니다. 스크린샷 3의 저장 수는 읽을 수 없어 "
            "판단에서 제외했습니다."
        ),
    },
    "next_actions": [
        {
            "order": 1,
            "title": "첫 3초를 결과 장면으로 시작",
            "description": "완성품의 빛 반사 컷을 맨 앞으로 옮기고 제작 과정은 그 다음에 배치합니다.",
        },
        {
            "order": 2,
            "title": "자막 크기와 위치 조정",
            "description": "핵심 메시지 자막을 화면 중앙 상단에 크게 배치해 무음 시청에서도 읽히게 합니다.",
        },
        {
            "order": 3,
            "title": "길이를 20초 이내로 단축",
            "description": "유지율 하락 구간 이후 컷을 제거하고 CTA를 앞당깁니다.",
        },
        {
            "order": 4,
            "title": "저장 유도 문구 추가",
            "description": "마지막 2초에 '색 조합 저장해두기' 자막을 넣어 저장 지표를 확인 가능하게 만듭니다.",
        },
    ],
    "tone": {
        "keywords": ["명확한", "빠른 훅", "따뜻한 색감"],
        "description": "무드는 유지하되 초반 정보 밀도를 높입니다. 첫 컷은 설명 없이 결과부터 보여줍니다.",
    },
}

# ------------------------------------------------------------------ error fixtures

ERROR_CASES: list[tuple[str, SosuError]] = [
    (
        "error.invalid_request.json",
        SosuError(
            ErrorCode.INVALID_REQUEST,
            "payload가 계약(SurveyDiagnosisRequestV1/PrescriptionRequestV1)과 일치하지 않습니다.",
            details=[
                {
                    "loc": ["answers", "q19_anything"],
                    "msg": "Extra inputs are not permitted",
                    "type": "extra_forbidden",
                }
            ],
        ),
    ),
    (
        "error.insufficient_input.json",
        SosuError(
            ErrorCode.INSUFFICIENT_INPUT,
            "문진 답변이 하나도 없고 제품 이미지도 없습니다. 답변 또는 이미지 중 하나는 필요합니다.",
            details=[{"reason": "no_answers_and_no_image"}],
        ),
    ),
    (
        "error.invalid_image_type.json",
        SosuError(
            ErrorCode.INVALID_IMAGE_TYPE,
            "지원하지 않는 이미지 형식입니다. image/jpeg, image/png, image/webp만 허용됩니다.",
            details=[{"content_type": "image/gif", "accepted": sorted(ACCEPTED_IMAGE_TYPES)}],
        ),
    ),
    (
        "error.image_too_large.json",
        SosuError(
            ErrorCode.IMAGE_TOO_LARGE,
            "product_image 이미지가 허용 용량을 초과했습니다.",
            details=[{"limit_bytes": PRODUCT_IMAGE_MAX_BYTES, "field": "product_image"}],
        ),
    ),
    (
        "error.invalid_image_count.json",
        SosuError(
            ErrorCode.INVALID_IMAGE_COUNT,
            f"Insight 스크린샷은 정확히 {INSIGHT_IMAGE_COUNT}장이어야 합니다.",
            details=[{"expected": INSIGHT_IMAGE_COUNT, "actual": 2}],
        ),
    ),
    (
        "error.invalid_instagram_url.json",
        SosuError(
            ErrorCode.INVALID_INSTAGRAM_URL,
            "Instagram Reel URL 형식이 아닙니다.",
            details=[{"loc": ["payload", "instagram_url"]}],
        ),
    ),
    (
        "error.model_timeout.json",
        SosuError(ErrorCode.MODEL_TIMEOUT, "모델 응답이 제한 시간 내에 도착하지 않았습니다."),
    ),
    (
        "error.model_provider_error.json",
        SosuError(ErrorCode.MODEL_PROVIDER_ERROR, "모델 제공자 호출에 실패했습니다."),
    ),
    (
        "error.model_schema_error.json",
        SosuError(
            ErrorCode.MODEL_SCHEMA_ERROR,
            "모델 출력이 예상 스키마와 일치하지 않습니다.",
            details=[{"loc": ["priorities"], "msg": "List should have at least 3 items"}],
        ),
    ),
    (
        "error.model_content_error.json",
        SosuError(
            ErrorCode.MODEL_CONTENT_ERROR,
            "모델이 사용 가능한 내용을 생성하지 못했습니다.",
            details=[{"finish_reason": "SAFETY"}],
        ),
    ),
    (
        "error.repair_failed.json",
        SosuError(
            ErrorCode.REPAIR_FAILED,
            "생성 결과가 검증을 통과하지 못했고 1회 보정 후에도 실패했습니다.",
            details=["reel_types[1].reason violates creator constraint: voice not allowed"],
        ),
    ),
    (
        "error.internal_error.json",
        SosuError(ErrorCode.INTERNAL_ERROR, GENERIC_INTERNAL_MESSAGE, retryable=False),
    ),
]


def _dump(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8"
    )


def _error_table() -> str:
    rows = ["| code | HTTP | retryable |", "|---|---:|---|"]
    for code in ErrorCode:
        err = SosuError(code, "x")
        rows.append(f"| `{code.value}` | {err.http_status} | {str(err.retryable).lower()} |")
    return "\n".join(rows)


def _catalog_table() -> str:
    rows = ["| question | field | label → code |", "|---|---|---|"]
    for q, meta in catalog_as_json()["questions"].items():  # type: ignore[union-attr]
        pairs = ", ".join(f"{o['label']}→`{o['code']}`" for o in meta["options"])
        cap = "single" if meta["selection"] == "single" else f"max {meta['max_selection']}"
        rows.append(f"| {q} ({cap}) | `{meta['field']}` | {pairs} |")
    return "\n".join(rows)


def _alias_table() -> str:
    rows = ["| question | SSOT code | CONTRACT V1 code |", "|---|---|---|"]
    for q, aliases in SSOT_CODE_ALIASES.items():
        for ssot, v1 in aliases.items():
            rows.append(f"| {q} | `{ssot}` | `{v1}` |")
    return "\n".join(rows)


def render_readme() -> str:
    fixtures = sorted(p.name for p in FIXTURES_DIR.glob("*.json"))
    fixture_list = "\n".join(f"- `fixtures/{name}`" for name in fixtures)
    return f"""# SOSU AI Service — Frontend Contract (v1.0)

This directory is the **only** interface between `web/` and the Python AI service.

- `openapi.json` — exported from the running FastAPI app (`uv run python scripts/export_openapi.py`).
- `fixtures/*.json` — deterministic request/response examples generated from the runtime Pydantic
  models (`uv run python scripts/make_fixtures.py`). Never hand-edit.

Base URL (dev): `http://127.0.0.1:8000`. CORS allows `http://localhost:5173`.

## Endpoints

### `GET /api/v1/health`
Plain JSON (not enveloped): `{{"status":"ok","service":"sosu-ai","contract_version":"1.0","gemini_configured":true|false}}`

### `POST /api/v1/diagnosis` — `multipart/form-data`
| field | type | rule |
|---|---|---|
| `payload` | text | JSON string of `SurveyDiagnosisRequestV1` (see `fixtures/diagnosis.request.json`) |
| `product_image` | file | optional, 0..1, `{" / ".join(sorted(ACCEPTED_IMAGE_TYPES))}`, ≤ {PRODUCT_IMAGE_MAX_BYTES:,} bytes |

Rules: `q19_*` must not be sent (rejected). Categorical lists max 3 (`q6,q9,q10,q11,q16,q17`).
`q18_disclosure` single value. Request is rejected with `INSUFFICIENT_INPUT` only when *no* answer
is given *and* no image is attached.

Success: `SuccessEnvelope<DiagnosisReportV1>` (`fixtures/diagnosis.success.json`).

### `POST /api/v1/prescription` — `multipart/form-data`
| field | type | rule |
|---|---|---|
| `payload` | text | JSON string of `PrescriptionRequestV1` (`fixtures/prescription.request.json`) |
| `insight_images` | file × {INSIGHT_IMAGE_COUNT} | exactly {INSIGHT_IMAGE_COUNT}, `{" / ".join(sorted(ACCEPTED_IMAGE_TYPES))}`, each ≤ {INSIGHT_IMAGE_MAX_BYTES:,} bytes, combined ≤ {INSIGHT_IMAGES_MAX_TOTAL_BYTES:,} bytes |

`instagram_url` must be an individual Instagram Reel URL (`/reel/<shortcode>` or `/reels/<shortcode>`; `/p/` posts are rejected). It is a context identifier only — v1 never
crawls it; the screenshots are the evidence.

Success: `SuccessEnvelope<PrescriptionReportV1>` (`fixtures/prescription.success.json`).

## UI labels → stable codes
The frontend renders Korean labels and must send the stable codes below (machine-readable copy:
`fixtures/ui_option_catalog.json`). `q10` and `q11` share labels but are separate fields/enums.

{_catalog_table()}

## SSOT code aliases
`SSOT/SOSU_AI_SERVICE_SSOT_FINAL_20260913.md` §5 spells some codes differently. The wire accepts
**only** the CONTRACT V1 codes; translate as follows:

{_alias_table()}

## Headers
- Request `X-Request-ID` (optional, ≤ 64 chars `[A-Za-z0-9._-]`) is echoed; otherwise the server
  generates one. Always present on the response and inside the envelope.

## Envelope
```json
{{"ok": true, "request_id": "...", "contract_version": "1.0", "data": {{...}}}}
{{"ok": false, "request_id": "...", "contract_version": "1.0",
 "error": {{"code": "...", "message": "...", "retryable": false, "details": []}}}}
```

## Error codes
{_error_table()}

`details` is a free-form list (validation locs, limits). `message` is safe to show; provider
exception text is never forwarded.

## Fixtures
{fixture_list}
"""


def main() -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    diag_req = SurveyDiagnosisRequestV1.model_validate(DIAGNOSIS_REQUEST)
    _dump(FIXTURES_DIR / "diagnosis.request.json", diag_req.model_dump(mode="json"))

    diag_env = SuccessEnvelope[DiagnosisReportV1](
        request_id="fixture-diagnosis-001",
        data=DiagnosisReportV1.model_validate(DIAGNOSIS_REPORT),
    )
    _dump(FIXTURES_DIR / "diagnosis.success.json", diag_env.model_dump(mode="json"))

    pres_req = PrescriptionRequestV1.model_validate(PRESCRIPTION_REQUEST)
    _dump(FIXTURES_DIR / "prescription.request.json", pres_req.model_dump(mode="json"))

    pres_env = SuccessEnvelope[PrescriptionReportV1](
        request_id="fixture-prescription-001",
        data=PrescriptionReportV1.model_validate(PRESCRIPTION_REPORT),
    )
    _dump(FIXTURES_DIR / "prescription.success.json", pres_env.model_dump(mode="json"))

    for name, err in ERROR_CASES:
        rid = "fixture-" + name.removeprefix("error.").removesuffix(".json").replace("_", "-")
        _dump(FIXTURES_DIR / name, envelope_for(err, rid).model_dump(mode="json"))

    _dump(FIXTURES_DIR / "ui_option_catalog.json", catalog_as_json())

    README_PATH.write_text(render_readme(), encoding="utf-8")
    print(f"wrote {len(ERROR_CASES) + 5} fixtures + contracts/README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
