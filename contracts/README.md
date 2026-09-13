# SOSU AI Service — Frontend Contract (v1.0)

This directory is the **only** interface between `web/` and the Python AI service.

- `openapi.json` — exported from the running FastAPI app (`uv run python scripts/export_openapi.py`).
- `fixtures/*.json` — deterministic request/response examples generated from the runtime Pydantic
  models (`uv run python scripts/make_fixtures.py`). Never hand-edit.

Base URL (dev): `http://127.0.0.1:8000`. CORS allows `http://localhost:5173`.

## Endpoints

### `GET /api/v1/health`
Plain JSON (not enveloped): `{"status":"ok","service":"sosu-ai","contract_version":"1.0","gemini_configured":true|false}`

### `POST /api/v1/diagnosis` — `multipart/form-data`
| field | type | rule |
|---|---|---|
| `payload` | text | JSON string of `SurveyDiagnosisRequestV1` (see `fixtures/diagnosis.request.json`) |
| `product_image` | file | optional, 0..1, `image/jpeg / image/png / image/webp`, ≤ 1,250,000 bytes |

Rules: `q19_*` must not be sent (rejected). Categorical lists max 3 (`q6,q9,q10,q11,q16,q17`).
`q18_disclosure` single value. Request is rejected with `INSUFFICIENT_INPUT` only when *no* answer
is given *and* no image is attached.

Success: `SuccessEnvelope<DiagnosisReportV1>` (`fixtures/diagnosis.success.json`).

### `POST /api/v1/prescription` — `multipart/form-data`
| field | type | rule |
|---|---|---|
| `payload` | text | JSON string of `PrescriptionRequestV1` (`fixtures/prescription.request.json`) |
| `insight_images` | file × 3 | exactly 3, `image/jpeg / image/png / image/webp`, each ≤ 900,000 bytes, combined ≤ 2,700,000 bytes |

`instagram_url` must be an individual Instagram Reel URL (`/reel/<shortcode>` or `/reels/<shortcode>`; `/p/` posts are rejected). It is a context identifier only — v1 never
crawls it; the screenshots are the evidence.

Success: `SuccessEnvelope<PrescriptionReportV1>` (`fixtures/prescription.success.json`).

## UI labels → stable codes
The frontend renders Korean labels and must send the stable codes below (machine-readable copy:
`fixtures/ui_option_catalog.json`). `q10` and `q11` share labels but are separate fields/enums.

| question | field | label → code |
|---|---|---|
| q6 (max 3) | `q6_product_appeals` | 디자인→`design`, 색감→`color`, 디테일→`detail`, 질감→`texture`, 소재→`material`, 제작 과정→`process`, 스토리→`story`, 희소성→`rarity`, 기타→`other` |
| q9 (max 3) | `q9_purchase_motives` | 예뻐서→`aesthetic`, 특별해서→`specialness`, 나를 위해→`self_reward`, 선물하려고→`gift`, 추억을 간직하려고→`memories`, 공간을 꾸미려고→`space_decor`, 나만의 것을 갖고 싶어서→`self_expression` |
| q10 (max 3) | `q10_desired_emotions` | 설렘→`excitement`, 행복→`happiness`, 따뜻함→`warmth`, 힐링→`healing`, 재미→`fun`, 특별함→`specialness`, 감동→`moved`, 위로→`comfort`, 기타→`other` |
| q11 (max 3) | `q11_brand_attributes` | 설렘→`excitement`, 행복→`happiness`, 따뜻함→`warmth`, 힐링→`healing`, 재미→`fun`, 특별함→`specialness`, 감동→`moved`, 위로→`comfort`, 기타→`other` |
| q16 (max 3) | `q16_pain_points` | 조회수가 안 나와요→`low_reach`, 팔로워가 안 늘어요→`low_follower_growth`, 어떤 콘텐츠를 만들지 모르겠어요→`ideation`, 촬영이 어려워요→`shooting_difficulty`, 편집이 어려워요→`editing_difficulty`, 꾸준히 올리기 어려워요→`consistency_difficulty`, 구매로 연결되지 않아요→`low_conversion`, 기타→`other` |
| q17 (max 3) | `q17_current_formats` | 거의 안 올려요→`rarely_post`, 완성품 위주→`finished_product`, 제작 과정 위주→`process`, 사진/영상 혼합→`photo_video_mix`, 트렌드 릴스→`trend_reels`, 브이로그→`vlog` |
| q18 (single) | `q18_disclosure` | 네→`yes`, 아니요→`no`, 얼굴만→`face_only`, 목소리만→`voice_only` |

## SSOT code aliases
`SSOT/SOSU_AI_SERVICE_SSOT_FINAL_20260913.md` §5 spells some codes differently. The wire accepts
**only** the CONTRACT V1 codes; translate as follows:

| question | SSOT code | CONTRACT V1 code |
|---|---|---|
| q6 | `making_process` | `process` |
| q9 | `special` | `specialness` |
| q9 | `memory` | `memories` |
| q9 | `space_styling` | `space_decor` |
| q9 | `unique_ownership` | `self_expression` |
| q10 | `being_moved` | `moved` |
| q11 | `being_moved` | `moved` |
| q16 | `low_views` | `low_reach` |
| q16 | `slow_follower_growth` | `low_follower_growth` |
| q16 | `content_ideation` | `ideation` |
| q16 | `filming` | `shooting_difficulty` |
| q16 | `editing` | `editing_difficulty` |
| q16 | `posting_consistency` | `consistency_difficulty` |
| q16 | `low_purchase_conversion` | `low_conversion` |
| q17 | `rarely_posts` | `rarely_post` |
| q17 | `making_process` | `process` |
| q18 | `face_and_voice` | `yes` |
| q18 | `neither` | `no` |

## Headers
- Request `X-Request-ID` (optional, ≤ 64 chars `[A-Za-z0-9._-]`) is echoed; otherwise the server
  generates one. Always present on the response and inside the envelope.

## Envelope
```json
{"ok": true, "request_id": "...", "contract_version": "1.0", "data": {...}}
{"ok": false, "request_id": "...", "contract_version": "1.0",
 "error": {"code": "...", "message": "...", "retryable": false, "details": []}}
```

## Error codes
| code | HTTP | retryable |
|---|---:|---|
| `INVALID_REQUEST` | 422 | false |
| `INSUFFICIENT_INPUT` | 422 | false |
| `INVALID_IMAGE_TYPE` | 415 | false |
| `IMAGE_TOO_LARGE` | 413 | false |
| `INVALID_IMAGE_COUNT` | 422 | false |
| `INVALID_INSTAGRAM_URL` | 422 | false |
| `MODEL_TIMEOUT` | 504 | true |
| `MODEL_PROVIDER_ERROR` | 502 | true |
| `MODEL_SCHEMA_ERROR` | 502 | true |
| `MODEL_CONTENT_ERROR` | 502 | true |
| `REPAIR_FAILED` | 502 | true |
| `INTERNAL_ERROR` | 500 | false |

`details` is a free-form list (validation locs, limits). `message` is safe to show; provider
exception text is never forwarded.

## Fixtures
- `fixtures/diagnosis.request.json`
- `fixtures/diagnosis.success.json`
- `fixtures/error.image_too_large.json`
- `fixtures/error.insufficient_input.json`
- `fixtures/error.internal_error.json`
- `fixtures/error.invalid_image_count.json`
- `fixtures/error.invalid_image_type.json`
- `fixtures/error.invalid_instagram_url.json`
- `fixtures/error.invalid_request.json`
- `fixtures/error.model_content_error.json`
- `fixtures/error.model_provider_error.json`
- `fixtures/error.model_schema_error.json`
- `fixtures/error.model_timeout.json`
- `fixtures/error.repair_failed.json`
- `fixtures/prescription.request.json`
- `fixtures/prescription.success.json`
- `fixtures/ui_option_catalog.json`
