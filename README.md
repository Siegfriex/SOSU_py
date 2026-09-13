# SOSU AI Service (`SOSU_py`)

Python / FastAPI / Gemini service for SOSU — Instagram Reels 진단(문진표) · 처방(Insight 스크린샷) for
small handcraft brands. Lives inside the `sosu` monorepo as its own workspace.

## Ownership boundary

- This directory (`SOSU_py/**`) is the AI/Python service. The Vite + React frontend lives in `../web`
  and is owned by a different agent/session — never edited from here.
- The **only** interface with the frontend is `contracts/openapi.json` + `contracts/fixtures/*`
  (see `contracts/README.md`). Both are generated from the runtime models; never hand-edit.

## Run

```bash
cp .env.example .env.local        # then paste your GEMINI_API_KEY into .env.local (gitignored)
uv sync                           # Python 3.12, deps from pyproject/uv.lock
uv run uvicorn app.main:app --reload --port 8000
```

Verify:

- `GET http://127.0.0.1:8000/api/v1/health` → `{"status":"ok","service":"sosu-ai","contract_version":"1.0","gemini_configured":false}`
- `http://127.0.0.1:8000/docs`

`gemini_configured` stays `false` while the key is the placeholder; no live Gemini call is made in
that state (requests to `/diagnosis` and `/prescription` fail with a typed `MODEL_*` error).

## Endpoints

| method | path | body |
|---|---|---|
| GET | `/api/v1/health` | — |
| POST | `/api/v1/diagnosis` | `multipart/form-data`: `payload` (JSON `SurveyDiagnosisRequestV1`), `product_image` (0..1) |
| POST | `/api/v1/prescription` | `multipart/form-data`: `payload` (JSON `PrescriptionRequestV1`), `insight_images` (exactly 3) |

## Quality gates

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy
uv run python scripts/check_openapi.py       # contracts/openapi.json == runtime
```

Regenerate contract artifacts after any model/endpoint change:

```bash
uv run python scripts/export_openapi.py
uv run python scripts/make_fixtures.py
uv run python scripts/release_shared_contract.py          # → ../contracts/{01_DOMAIN_CONTRACT.md,02_openapi.json,03_CONTRACT_FIXTURES.json}
uv run python scripts/release_shared_contract.py --check  # exit 1 if the shared release is stale
```

`../contracts/` (monorepo root) is the **shared contract release** the frontend consumes — exactly
three generated files. `SOSU_py/contracts/` stays as backend test infrastructure.

Live Gemini smoke tests are skipped unless both a real key is present in `.env.local` and:

```bash
RUN_LIVE_GEMINI_TESTS=1 uv run pytest tests/test_live_gemini.py
```

## Layout

```
app/
  config.py            Settings (env only; no hardcoded keys/models)
  contracts/           public Pydantic contract V1 (enums, requests, reports, envelope)
  domain/              normalizer, evidence models, inference policy, validator, errors
  images/              Pillow normalization + ingress limits
  gemini/              GeminiGateway protocol, google-genai client, versioned prompts
  services/            diagnosis / prescription orchestration (observe → synthesize → validate → repair×1)
  api/                 FastAPI router, deps, error envelope
  main.py              app factory
contracts/             openapi.json + fixtures (backend test infrastructure)
scripts/               export_openapi / check_openapi / make_fixtures / release_shared_contract
tests/
SSOT/                  product/inference SSOT (owner-provided); CONTRACT V1 wins on conflicts
```
