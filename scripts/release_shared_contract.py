# ruff: noqa: E501  -- Korean contract prose lines are intentionally long
"""Shared contract release → <monorepo>/contracts/ (exactly three artifacts).

    01_DOMAIN_CONTRACT.md      human contract, generated from runtime V1 names (never hand-edit)
    02_openapi.json            FastAPI runtime OpenAPI (identical to SOSU_py/contracts/openapi.json)
    03_CONTRACT_FIXTURES.json  frontend integration fixtures projected from the backend fixtures

Usage:  uv run python scripts/release_shared_contract.py [--check] [--out DIR]
Default DIR = $SOSU_SHARED_CONTRACT_DIR or <SOSU_py>/../contracts. SOSU_py/contracts/* stays as
the test infrastructure; this directory is the only thing the frontend needs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.errors import envelope_for  # noqa: E402
from app.config import CONTRACT_VERSION, Settings  # noqa: E402
from app.contracts.catalog import (  # noqa: E402
    CATALOG_ENUM_TYPES,
    UI_OPTION_CATALOG,
    catalog_as_json,
)
from app.contracts.diagnosis import (  # noqa: E402
    MAX_CHOICES,
    MAX_TEXT_LEN,
    DiagnosisReportV1,
    SurveyDiagnosisRequestV1,
)
from app.contracts.envelope import ErrorCode, SuccessEnvelope  # noqa: E402
from app.contracts.prescription import PrescriptionReportV1, PrescriptionRequestV1  # noqa: E402
from app.domain.errors import SosuError  # noqa: E402
from app.domain.normalizer import SAFE_MAX_TEXT_LEN  # noqa: E402
from app.images.types import (  # noqa: E402
    ACCEPTED_IMAGE_TYPES,
    INSIGHT_IMAGE_COUNT,
    INSIGHT_IMAGE_MAX_BYTES,
    INSIGHT_IMAGES_MAX_TOTAL_BYTES,
    PRODUCT_IMAGE_MAX_BYTES,
)
from app.main import create_app  # noqa: E402

from scripts.make_fixtures import (  # noqa: E402
    DIAGNOSIS_REPORT,
    DIAGNOSIS_REQUEST,
    ERROR_CASES,
    PRESCRIPTION_REPORT,
    PRESCRIPTION_REQUEST,
)

ARTIFACTS = ("01_DOMAIN_CONTRACT.md", "02_openapi.json", "03_CONTRACT_FIXTURES.json")

# Which error codes each endpoint can actually emit.
DIAGNOSIS_ERROR_CODES: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.INVALID_REQUEST,
        ErrorCode.INSUFFICIENT_INPUT,
        ErrorCode.INVALID_IMAGE_TYPE,
        ErrorCode.IMAGE_TOO_LARGE,
        ErrorCode.MODEL_TIMEOUT,
        ErrorCode.MODEL_PROVIDER_ERROR,
        ErrorCode.MODEL_SCHEMA_ERROR,
        ErrorCode.MODEL_CONTENT_ERROR,
        ErrorCode.REPAIR_FAILED,
        ErrorCode.INTERNAL_ERROR,
    }
)
PRESCRIPTION_ERROR_CODES: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.INVALID_REQUEST,
        ErrorCode.INVALID_IMAGE_TYPE,
        ErrorCode.IMAGE_TOO_LARGE,
        ErrorCode.INVALID_IMAGE_COUNT,
        ErrorCode.INVALID_INSTAGRAM_URL,
        ErrorCode.MODEL_TIMEOUT,
        ErrorCode.MODEL_PROVIDER_ERROR,
        ErrorCode.MODEL_SCHEMA_ERROR,
        ErrorCode.MODEL_CONTENT_ERROR,
        ErrorCode.REPAIR_FAILED,
        ErrorCode.INTERNAL_ERROR,
    }
)

# Q → request field (runtime V1 names). Q19 is intentionally absent.
QUESTION_FIELDS: list[tuple[str, str, str, str]] = [
    ("Q1", "q1_brand_name", "text", "브랜드 이름"),
    ("Q2", "q2_product_category", "text", "제품군"),
    ("Q3", "q3_hero_product", "text", "가장 자신 있는 제품"),
    ("Q4", "q4_materials", "text", "주 소재"),
    ("Q5", "q5_material_reason", "text", "소재를 쓰는 이유"),
    ("Q6", "q6_product_appeals", "multi ≤3", "제품의 가장 큰 매력"),
    ("Q7", "q7_differentiation", "text", "차별점"),
    ("Q8", "q8_target_customer", "text", "제품을 가장 좋아할 사람"),
    ("Q9", "q9_purchase_motives", "multi ≤3", "구매 이유"),
    ("Q10", "q10_desired_emotions", "multi ≤3", "고객이 느꼈으면 하는 기분"),
    ("Q11", "q11_brand_attributes", "multi ≤3", "브랜드를 표현하는 단어"),
    ("Q12", "q12_avoidance", "text", "피하고 싶은 이미지"),
    ("Q13", "q13_motif", "text", "상징/모티프"),
    ("Q14", "q14_primary_message", "text", "가장 어필하고 싶은 것"),
    ("Q15", "q15_interesting_process", "text", "신기해할 제작 과정"),
    ("Q16", "q16_pain_points", "multi ≤3", "인스타그램에서 어려운 점"),
    ("Q17", "q17_current_formats", "multi ≤3", "현재 올리는 릴스"),
    ("Q18", "q18_disclosure", "single", "얼굴/목소리 공개 가능 여부"),
    ("Q20", "q20_must_show", "text", "꼭 보여주고 싶은 것"),
]

_TEXT_FIELDS = {f for _, f, kind, _ in QUESTION_FIELDS if kind == "text"}
_LIST_FIELDS = {f for _, f, kind, _ in QUESTION_FIELDS if kind.startswith("multi")}


# --------------------------------------------------------------------------- builders


def build_openapi() -> dict[str, Any]:
    return create_app().openapi()


def _error_envelopes(codes: frozenset[ErrorCode], prefix: str) -> dict[str, dict[str, Any]]:
    """{retryable|non_retryable: {CODE: ErrorEnvelope}} using the backend's own error cases."""
    groups: dict[str, dict[str, Any]] = {"retryable": {}, "non_retryable": {}}
    for name, err in ERROR_CASES:
        if err.code not in codes:
            continue
        rid = f"fixture-{prefix}-" + name.removeprefix("error.").removesuffix(".json").replace(
            "_", "-"
        )
        bucket = "retryable" if err.retryable else "non_retryable"
        groups[bucket][err.code.value] = envelope_for(err, rid).model_dump(mode="json")
    return groups


def build_fixtures() -> dict[str, Any]:
    diag_req = SurveyDiagnosisRequestV1.model_validate(DIAGNOSIS_REQUEST)
    diag_env = SuccessEnvelope[DiagnosisReportV1](
        request_id="fixture-diagnosis-001", data=DiagnosisReportV1.model_validate(DIAGNOSIS_REPORT)
    )
    pres_req = PrescriptionRequestV1.model_validate(PRESCRIPTION_REQUEST)
    pres_env = SuccessEnvelope[PrescriptionReportV1](
        request_id="fixture-prescription-001",
        data=PrescriptionReportV1.model_validate(PRESCRIPTION_REPORT),
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_by": "SOSU_py/scripts/release_shared_contract.py",
        "diagnosis": {
            "endpoint": "POST /api/v1/diagnosis",
            "request": diag_req.model_dump(mode="json"),
            "success": diag_env.model_dump(mode="json"),
            "errors": _error_envelopes(DIAGNOSIS_ERROR_CODES, "diagnosis"),
        },
        "prescription": {
            "endpoint": "POST /api/v1/prescription",
            "request": pres_req.model_dump(mode="json"),
            "success": pres_env.model_dump(mode="json"),
            "errors": _error_envelopes(PRESCRIPTION_ERROR_CODES, "prescription"),
        },
        "ui_option_catalog": catalog_as_json(),
    }


def _enum_registry() -> str:
    out: list[str] = []
    for q, table in UI_OPTION_CATALOG.items():
        enum_type = CATALOG_ENUM_TYPES[q]
        field = next(f for qq, f, _, _ in QUESTION_FIELDS if qq.lower() == q)
        out.append(f"### {q.upper()} — `{field}` → `{enum_type.__name__}`")
        out.append("")
        out.append("| 한글 UI label | code |")
        out.append("|---|---|")
        out.extend(f"| {label} | `{code.value}` |" for label, code in table.items())
        out.append("")
    return "\n".join(out)


def _question_table() -> str:
    rows = ["| Q | request field | 입력 종류 | 의미 | 처리 |", "|---|---|---|---|---|"]
    for q, field, kind, meaning in QUESTION_FIELDS:
        if kind == "text":
            proc = "natural text — 원문 보존 (아래 §3)"
        elif kind == "single":
            proc = "categorical single — `CreatorDisclosure` code 1개 또는 `null`"
        else:
            proc = f"categorical multi — enum code 목록, 최대 {MAX_CHOICES}개"
        rows.append(f"| {q} | `{field}` | {kind} | {meaning} | {proc} |")
    return "\n".join(rows)


def _error_table() -> str:
    rows = [
        "| error.code | HTTP | retryable | 발생 endpoint | 의미 / 프론트 처리 |",
        "|---|---:|---|---|---|",
    ]
    meaning: dict[ErrorCode, str] = {
        ErrorCode.INVALID_REQUEST: "payload JSON이 계약과 불일치(q19 포함, 알 수 없는 필드, enum 외 코드, 4개 이상 선택 등). `details[].loc`로 필드 표시",
        ErrorCode.INSUFFICIENT_INPUT: "문진 답변이 하나도 없고 이미지도 없음. 문진으로 복귀",
        ErrorCode.INVALID_IMAGE_TYPE: "허용되지 않는 MIME 또는 디코딩 불가. 업로드 영역 오류",
        ErrorCode.IMAGE_TOO_LARGE: "파일/합산 용량 초과. 브라우저 재압축 후 재시도",
        ErrorCode.INVALID_IMAGE_COUNT: "처방전 스크린샷이 정확히 3장이 아님",
        ErrorCode.INVALID_INSTAGRAM_URL: "개별 Reel URL이 아님(/p/, 프로필, 타 도메인 등)",
        ErrorCode.MODEL_TIMEOUT: "단계 timeout 또는 전체 deadline 초과. 입력 유지한 채 공통 retry",
        ErrorCode.MODEL_PROVIDER_ERROR: "Gemini upstream 오류. 공통 retry",
        ErrorCode.MODEL_SCHEMA_ERROR: "모델 출력이 JSON 스키마 불일치. 공통 retry",
        ErrorCode.MODEL_CONTENT_ERROR: "모델이 유효한 내용을 반환하지 못함(안전 차단, 토큰 초과 등). 공통 retry",
        ErrorCode.REPAIR_FAILED: "1회 수리 후에도 의미 검증 실패. 공통 retry",
        ErrorCode.INTERNAL_ERROR: "서버 내부 오류. 공통 오류 화면",
    }
    for code in ErrorCode:
        err = SosuError(code, "x")
        eps = []
        if code in DIAGNOSIS_ERROR_CODES:
            eps.append("diagnosis")
        if code in PRESCRIPTION_ERROR_CODES:
            eps.append("prescription")
        rows.append(
            f"| `{code.value}` | {err.http_status} | {str(err.retryable).lower()} | {', '.join(eps)} | {meaning[code]} |"
        )
    return "\n".join(rows)


def build_domain_contract() -> str:
    s = Settings()
    mimes = " / ".join(f"`{m}`" for m in sorted(ACCEPTED_IMAGE_TYPES))
    return f"""# SOSU AI Service — Domain Contract V{CONTRACT_VERSION} (frozen)

생성: `SOSU_py/scripts/release_shared_contract.py` (런타임 모델에서 생성 — 수동 편집 금지)
동반 artifact: `02_openapi.json`(FastAPI 런타임 스키마), `03_CONTRACT_FIXTURES.json`(통합 fixture)
이 세 파일이 `web/` ↔ `SOSU_py/` 사이의 **유일한** 계약이다. 프론트는 이 밖의 백엔드 내부(EvidencePack, 프롬프트, 검증기)를 알 필요가 없다 (§12).

---

## 1. Endpoint 의미

| endpoint | 의미 | 입력 | 성공 출력 |
|---|---|---|---|
| `GET /api/v1/health` | 서비스 생존 + Gemini 키 구성 여부. 봉투 없음 | — | `{{"status":"ok","service":"sosu-ai","contract_version":"{CONTRACT_VERSION}","gemini_configured":bool}}` |
| `POST /api/v1/diagnosis` | **문진표 → 릴스 진단서.** 설문 답변(+선택 제품 이미지 1장)을 받아 `DiagnosisReportV1`을 동기 반환 | `multipart/form-data`: `payload`(JSON 문자열 `SurveyDiagnosisRequestV1`), `product_image`(파일, 0..1) | `SuccessEnvelope<DiagnosisReportV1>` |
| `POST /api/v1/prescription` | **릴스 처방전.** Reel URL + Insight 스크린샷 정확히 3장을 받아 `PrescriptionReportV1`을 동기 반환 | `multipart/form-data`: `payload`(JSON 문자열 `PrescriptionRequestV1`), `insight_images`(파일 ×{INSIGHT_IMAGE_COUNT}) | `SuccessEnvelope<PrescriptionReportV1>` |

- 두 POST는 **동기 요청 1회**다. 진행률 이벤트(SSE/WebSocket/job polling)는 v1 계약에 없다. 프론트는 indeterminate 로딩을 쓴다.
- 실행 시간 한도: 전체 deadline **{s.sosu_request_deadline_seconds:.0f}s** (단계별 observation {s.gemini_timeout_observe:.0f}s / synthesis {s.gemini_timeout_synthesis:.0f}s / repair {s.gemini_timeout_repair:.0f}s). 초과 시 `MODEL_TIMEOUT`. 클라이언트 AbortSignal은 {s.sosu_request_deadline_seconds:.0f}s보다 길게 잡는다.
- 요청 헤더 `X-Request-ID`(선택, ≤64자 `[A-Za-z0-9._-]`)는 그대로 에코되고 봉투의 `request_id`가 된다. 없으면 서버가 생성한다.
- CORS 허용 origin(dev): `{s.sosu_cors_origins}`.

`payload` 공통 필드: `contract_version`(반드시 `"{CONTRACT_VERSION}"`), `locale`(기본 `"ko-KR"`, 결과 언어).

## 2. Q1~Q18/Q20 → request field 매핑 (`payload.answers`)

{_question_table()}

- **모든 필드는 optional**이다(부분 제출 허용). 백엔드는 필수 문항을 만들지 않는다. 단, 답변이 하나도 없고 이미지도 없으면 `INSUFFICIENT_INPUT`.
- 알 수 없는 필드는 거부된다(`INVALID_REQUEST`). 이메일·버튼·탭·스텝 같은 앱 제어값은 `answers`에 넣지 않는다.

## 3. Natural text vs categorical 처리

| 종류 | 필드 | 프론트가 보내는 값 | 백엔드 처리 |
|---|---|---|---|
| natural text | {", ".join(f"`{f}`" for f in sorted(_TEXT_FIELDS, key=lambda x: int(x.split("_")[0][1:])))} | 사용자가 쓴 문자열 그대로 (`null`/빈 문자열 허용, 최대 {MAX_TEXT_LEN:,}자) | **의미를 바꾸지 않는다.** Unicode NFC, 앞뒤 공백 제거, CRLF→LF, 빈값→`null`, {SAFE_MAX_TEXT_LEN:,}자 안전 길이만 적용. 요약·키워드 추출·번역 없음. 이 원문이 그대로 AI 근거가 된다 |
| categorical multi | {", ".join(f"`{f}`" for f in sorted(_LIST_FIELDS, key=lambda x: int(x.split("_")[0][1:])))} | stable code 문자열 배열 (한글 label을 보내지 않는다) | enum 검증, 중복 제거, 최대 {MAX_CHOICES}개. label→code 표는 §4 / `03_CONTRACT_FIXTURES.json#ui_option_catalog` |
| categorical single | `q18_disclosure` | code 1개 또는 `null` | hard constraint로 파생 (§6) |

## 4. Stable enum registry (code ↔ 한글 UI label)

프론트는 label을 렌더하고 **code를 전송**한다. 표기는 프론트 `questions.ts`의 options 문자열과 동일하다(Q17 정식 label = `사진/영상 혼합`).

{_enum_registry()}
`other`(기타)를 골라도 별도 자유입력 필드(`*_other_text`)는 **v1에 없다**. 기타의 내용은 인접 자연어 문항(예: Q7/Q14)에 쓰도록 UI에서 안내한다.

## 5. Q10 / Q11 namespace 분리

`q10_desired_emotions`(`DesiredEmotion`)와 `q11_brand_attributes`(`BrandAttribute`)는 **같은 한글 label과 같은 code 문자열**을 쓰지만 별개의 필드·별개의 enum 타입이다. Q10은 *고객이 느낄 감정*, Q11은 *브랜드가 갖고 싶은 속성*으로 AI가 다르게 해석한다. 프론트에서 하나의 선택 상태를 두 필드에 복사하지 말 것.

## 6. Q18 hard constraint 의미

`q18_disclosure` → 백엔드가 `face_allowed`/`voice_allowed`를 파생하고 **AI 추천이 이를 위반하면 결과를 반환하지 않는다**(1회 수리 후 실패 시 `REPAIR_FAILED`).

| code | UI label | face_allowed | voice_allowed |
|---|---|---|---|
| `yes` | 네 | true | true |
| `no` | 아니요 | false | false |
| `face_only` | 얼굴만 | true | false |
| `voice_only` | 목소리만 | false | true |
| `null` | 미응답 | 제약 없음 | 제약 없음 |

## 7. Q19 부재

Q19는 원본 문진에 존재하지 않는다. `answers`에 `q19_*` 필드가 있으면 `INVALID_REQUEST`로 거부된다. 문항 번호는 18 → 20으로 건너뛴다.

## 8. Media / count / size / MIME

| 용도 | multipart 필드 | 개수 | 허용 MIME | 크기 |
|---|---|---|---|---|
| 문진 제품 이미지 | `product_image` | **0..1** | {mimes} | 파일당 ≤ {PRODUCT_IMAGE_MAX_BYTES:,} bytes |
| 처방 Insight 스크린샷 | `insight_images` | **정확히 {INSIGHT_IMAGE_COUNT}** | {mimes} | 파일당 ≤ {INSIGHT_IMAGE_MAX_BYTES:,} bytes, 합산 ≤ {INSIGHT_IMAGES_MAX_TOTAL_BYTES:,} bytes |

- **PDF는 지원하지 않는다**(`INVALID_IMAGE_TYPE` 415). `image/jpg` 같은 비표준 MIME도 거부된다.
- 선언 MIME뿐 아니라 실제 바이트 포맷도 검사한다(GIF 바이트를 `image/png`로 보내면 거부).
- 서버는 이미지를 EXIF 회전 보정·RGB·축소·JPEG 재인코딩만 하며 저장하지 않는다. 브라우저 1차 압축은 권장이지만 계약 조건은 위 한도뿐이다.

## 9. Instagram URL 의미 (`PrescriptionRequestV1.instagram_url`)

- **개별 Reel URL만** 허용: `https://www.instagram.com/reel/<shortcode>/` (또는 `/reels/<shortcode>`; 호스트 `instagram.com`, `www.`, `m.`; 뒤 슬래시·쿼리스트링 허용).
- `/p/<shortcode>` 일반 게시물, `/tv/`, 프로필, 스토리, 타 도메인은 `INVALID_INSTAGRAM_URL`.
- v1 백엔드는 URL을 **크롤링하거나 열어보지 않는다.** 결과의 근거는 오직 스크린샷 3장이며 URL은 어떤 릴스에 대한 처방인지 표시하는 식별자일 뿐이다. 프론트는 "URL을 분석했다"는 문구를 쓰지 않는다.

## 10. Success / Error envelope 의미

```json
{{"ok": true,  "request_id": "…", "contract_version": "{CONTRACT_VERSION}", "data": {{ …DiagnosisReportV1 | PrescriptionReportV1… }}}}
{{"ok": false, "request_id": "…", "contract_version": "{CONTRACT_VERSION}", "error": {{"code": "…", "message": "…", "retryable": bool, "details": []}}}}
```

- `ok`로 분기한다. `ok:true`이면 `data`는 **완전한** 리포트다(부분 실패 섹션 없음; 스키마+의미 검증을 통과한 결과만 반환).
- `data.schema_version`은 `"diagnosis.v1"` / `"prescription.v1"`. `priorities`·`reel_types`는 정확히 3개, `next_actions`는 정확히 4개, `structure`는 5개 고정 슬롯(`hook_0_3, body_3_10, body_10_20, close_20_27, cta_27_30`).
- 리포트 값은 **데이터만** 담는다. 섹션 제목("추천 포지셔닝" 등)은 프론트 상수다.
- `error.message`는 사용자에게 보여도 되는 한국어 문장이다. 제공자 예외 텍스트는 절대 포함되지 않는다. `error.details`는 자유형 리스트(검증 위치, 한도 값 등)다.
- HTTP 404 등 라우팅 오류도 같은 봉투로 온다.

## 11. error.code + retryable 처리 규칙

{_error_table()}

규칙:
1. `retryable:true` → 입력(draft)을 보존한 채 같은 요청을 **그대로 재시도**할 수 있다(공통 "다시 시도" 화면). 백엔드 상태가 없으므로 멱등하다.
2. `retryable:false` → 재시도해도 같은 결과다. 입력을 고쳐야 한다(`details[].loc`/`field`로 어느 입력인지 표시).
3. 프론트는 `code`로만 분기한다. `message`는 표시용, HTTP status는 보조 신호다.
4. 클라이언트 측 timeout(AbortSignal)은 `MODEL_TIMEOUT`과 동일하게 취급한다.

## 12. 경계: 프론트가 알 필요 없는 것

프론트는 `02_openapi.json`의 public 모델(`SurveyDiagnosisRequestV1`, `PrescriptionRequestV1`, `DiagnosisReportV1`, `PrescriptionReportV1`, 봉투, `HealthResponse`)만 다룬다. 다음은 백엔드 내부이며 계약이 아니다: `DeclaredEvidenceV1`, `VisualObservationV1`, `InsightObservationV1`, `EvidencePackV1`, `InferencePolicyV1`, 프롬프트 버전, 검증기/수리 로직, Gemini 모델명·thinking·토큰 예산. 이들이 바뀌어도 이 계약은 바뀌지 않는다. 반대로 이 문서의 어떤 항목이 바뀌면 `contract_version`이 올라간다.
"""


# --------------------------------------------------------------------------- io


def default_out_dir() -> Path:
    env = os.environ.get("SOSU_SHARED_CONTRACT_DIR")
    return Path(env).resolve() if env else (ROOT.parent / "contracts").resolve()


def render_all() -> dict[str, str]:
    return {
        "01_DOMAIN_CONTRACT.md": build_domain_contract(),
        "02_openapi.json": json.dumps(build_openapi(), sort_keys=True, indent=2, ensure_ascii=False)
        + "\n",
        "03_CONTRACT_FIXTURES.json": json.dumps(build_fixtures(), indent=2, ensure_ascii=False)
        + "\n",
    }


def write_release(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    extras = sorted(p.name for p in out_dir.iterdir() if p.name not in ARTIFACTS)
    if extras:
        raise SystemExit(
            f"{out_dir} must contain exactly {ARTIFACTS}; found extra entries: {extras}"
        )
    written = []
    for name, content in render_all().items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def check_release(out_dir: Path) -> list[str]:
    problems: list[str] = []
    if not out_dir.is_dir():
        return [f"{out_dir} does not exist"]
    names = sorted(p.name for p in out_dir.iterdir())
    if names != sorted(ARTIFACTS):
        problems.append(f"expected exactly {sorted(ARTIFACTS)}, found {names}")
    for name, expected in render_all().items():
        path = out_dir / name
        if path.exists() and path.read_text(encoding="utf-8") != expected:
            problems.append(f"{name} is stale (re-run scripts/release_shared_contract.py)")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--check", action="store_true", help="verify the release matches runtime; exit 1 if not"
    )
    args = ap.parse_args(argv)
    out_dir = (args.out or default_out_dir()).resolve()
    if args.check:
        problems = check_release(out_dir)
        for p in problems:
            print("STALE:", p)
        print(f"{out_dir}: {'matches runtime' if not problems else 'MISMATCH'}")
        return 1 if problems else 0
    for path in write_release(out_dir):
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
