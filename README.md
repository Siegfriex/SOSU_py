# SOSU AI Service · `SOSU_py`

FastAPI + Gemini backend for **SOSU** — Instagram Reels consulting for small handcraft brands.
Two structured-generation workflows behind one versioned HTTP contract:

| Workflow | Input | Output |
|---|---|---|
| **진단 Diagnosis** | 20-question survey + up to 3 optional product photos | 9-section Reels diagnosis (positioning, strengths, target, tone, fonts, priorities, reel types, 30-second structure, final guidance) |
| **처방 Prescription** | Reel URL + exactly 3 Instagram Insight screenshots | Metric-grounded diagnosis of one reel + 4 next actions + tone |

Live: API `https://sosu-py.vercel.app` (`/api/v1/health`, `/api/v1/features`) · frontend `https://sosu-rosy.vercel.app`
— this repo is the `SOSU_py` submodule of [`Siegfriex/sosu`](https://github.com/Siegfriex/sosu).

## Pipeline

```
multipart (payload JSON + images)
  → request validation · image normalisation (type sniffing, size caps, re-encode)
  → [observe]   visual-observation-v1 / insight-observation-v2   (only when images are present)
  → [synthesise] diagnosis-v2 / prescription-v3  + guidebook KnowledgePack block (gb2-5edea367, 93 rules)
  → domain validator (placeholders, Q18 face/voice constraint, evidence grounding)
       PASS → response · REPAIRABLE → repair-v1 once → re-validate · FATAL → typed error
  → envelope {ok, request_id, contract_version, data | error}
```

- **One vendor boundary.** `app/gemini/client.py` is the only module importing the SDK; everything else depends on the
  `GeminiGateway` protocol, so tests and the dev server swap in a deterministic fake gateway.
- **Structured output only.** Every call uses a JSON schema derived from the Pydantic model, and the response is
  validated again server-side. A mismatch becomes `MODEL_SCHEMA_ERROR`; it is never passed to the client.
- **Deadline budget.** Each request has a 180 s budget. Every stage timeout and retry is capped at the remaining
  budget minus 2 s, and the request fails fast with `MODEL_TIMEOUT` when less than 3 s is left. This keeps the
  worst case at about 178 s, under the 200 s Vercel function limit (`docs/RD6_TIMEOUT.md`).
- **Grounding.**
  - Prompts mark what counts as evidence. Account handles are redacted, and on-screen text is labelled as
    "not video content".
  - The validator flags four kinds of content and sends the draft to one repair pass:
    - content inferred from the handle or URL,
    - claims about unseen video content,
    - claims of having watched the Reel,
    - numbers for metrics the observation marked unreadable.
  - Background: `docs/RD5_GROUNDING.md`.
- **Creator constraints.** Q18 (can the creator show their face / use their voice) is enforced by a keyword +
  negation-window checker, so "자막으로 대신" passes while "내레이션으로 설명" is repaired.

## Public-runtime safety

The service runs on a public URL, and every generation is a paid model call. Defaults are therefore fail-closed:

| Control | Where |
|---|---|
| AI routes return `503 SERVICE_UNAVAILABLE` on Vercel/production unless `SOSU_PUBLIC_INFERENCE_ENABLED=true` | `app/security/middleware.py` |
| Shared rate limit: 3 generation requests / 60 s / IP, diagnosis and prescription combined | Vercel Firewall rule; plain-text edge 429 is handled by the frontend |
| 4 MB request body cap, per-instance token bucket (defence in depth) | `app/security/*` |
| Monthly provider spend cap | Google AI Studio project setting |
| Email delivery (+ guidebook e-book link), image retention, external research | **off until configured**: implemented or designed, switched by env (`/api/v1/features`); setup guide `docs/EMAIL_SETUP_GUIDE.md` |
| No secrets in logs: only `request_id`, path, error code, token counts | `app/gemini/client.py`, `app/api/*` |

## Endpoints (contract `1.0`)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/health` | `gemini_configured` flag, contract version |
| GET | `/api/v1/features` | runtime flags (inference / email / image storage / research), knowledge version, build SHA |
| POST | `/api/v1/diagnosis` | multipart: `payload` (`SurveyDiagnosisRequestV1`), `product_image` repeated 0..3 |
| POST | `/api/v1/prescription` | multipart: `payload` (`PrescriptionRequestV1`), `insight_images` ×3 |
| POST | `/api/v1/report-email` | HMAC `delivery_token` bound to the generated report. Answers 503 while email is disabled |
| GET | `/api/v1/guidebook?t=…` | signed, expiring e-book link from report e-mails → 302 to the PDF (storage URL stays secret) |

Typed error codes (`INSUFFICIENT_INPUT`, `INVALID_IMAGE_COUNT`, `IMAGE_TOO_LARGE`, `MODEL_TIMEOUT`, `REPAIR_FAILED`,
`RATE_LIMITED`, `SERVICE_UNAVAILABLE`, …) each carry `retryable`; the frontend maps them to distinct screens.
`contracts/openapi.json` and `contracts/fixtures/*` are **generated** from the runtime models and released to the
monorepo as `../contracts/{01_DOMAIN_CONTRACT.md,02_openapi.json,03_CONTRACT_FIXTURES.json}`.

## Layout

```
app/
  api/          routes, delivery (email) endpoint
  contracts/    request/response models, envelope, error codes
  domain/       answer normaliser, input sufficiency, evidence packs, validator (Q18, grounding)
  gemini/       gateway protocol, google-genai client, prompts/
  images/       sniffing, normalisation
  knowledge/    KnowledgePack loader + prompt block
  research/     external research boundary (disabled)
  security/     public-runtime gate, rate limiter, delivery tokens, middleware
  services/     diagnosis / prescription orchestration, deadline budget
knowledge/      guidebook KnowledgePack (JSON + schema + coverage) and build/validate tools
scripts/        contract export/release, fake gateway + dev server, capped live smoke
tests/          pytest suite (deterministic; live tests opt-in)
docs/           design notes per topic (see docs/README.md)
```

## Run locally

```bash
cp .env.example .env.local     # put GEMINI_API_KEY in .env.local (gitignored)
uv sync                        # Python 3.12
uv run uvicorn app.main:app --reload --port 8000
```

Without a key, `gemini_configured=false` and generation fails fast with a typed `MODEL_PROVIDER_ERROR`, with no
network call.

**Deterministic dev server (no Gemini):**

```bash
.venv/bin/python scripts/serve_fake.py --port 8000   # binds 127.0.0.1 only; refuses SOSU_ENV=production
```

- This is the real `create_app()` (validation, prompts, validator, repair) with only the gateway replaced.
- Scenarios are selected through `/__fake__/scenario`: `success, timeout, provider_error, schema_error, repairable,
  repair_failed, fatal_content, slow`.
- The frontend's cross-stack integration suite runs against it.

## Quality gates

```bash
uv run pytest                      # 414 passed, 1 skipped (live test opt-in)
uv run ruff check && uv run ruff format --check
uv run mypy
uv run python scripts/check_openapi.py                    # committed contract == runtime
uv run python scripts/release_shared_contract.py --check  # monorepo contract release is current
uv run python knowledge/tools/validate_pack.py            # KnowledgePack schema + coverage
```

Live verification is opt-in and capped. `scripts/live_smoke.py` makes at most 8 provider calls (`docs/LIVE_SMOKE.md`).
Production browser E2E lives in the monorepo (`web/e2e`).

## Docs

`docs/README.md` indexes the topic notes: security, Vercel, email, image storage, knowledge, research boundary, live
smoke, RD-5 grounding, RD-6 timeouts.

## License

MIT © 2026 Siegfriex
