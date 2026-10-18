# Vercel packaging (backend `sosu-py`)

Deployed by Vercel's FastAPI zero-config from `SOSU_py` main; entrypoint `app/main.py` exporting
`app`. No deploy was performed in Phase 2 packaging; this documents the config we ship.

## vercel.json

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": {
    "app/main.py": {
      "maxDuration": 200,
      "excludeFiles": "{tests/**,SSOT/**,docs/**,.sprint/**}"
    }
  }
}
```

- `functions."app/main.py"` is the documented key for the FastAPI entrypoint (Vercel FastAPI docs).
- **maxDuration 200 s** = `SOSU_REQUEST_DEADLINE_SECONDS` (180) + 20 s margin, so our own deadline
  fires first and returns a structured `MODEL_TIMEOUT` instead of a platform 504.
  Plan limits: with Fluid compute (default for new projects), Hobby max is 300 s, Pro/Enterprise
  up to 800 s — **account plan not verified**. If the plan's limit is lower than 200 s the build/
  deploy fails with a maxDuration error → lower it to the limit and lower
  `SOSU_REQUEST_DEADLINE_SECONDS` to `limit − 20`.
- **Knowledge pack bundling:** Python functions bundle the project files by default (files are
  trimmed with `excludeFiles`, not opted-in with `includeFiles`), so
  `knowledge/guidebook/knowledgepack.v1.json` is included. The provider resolves it as
  `Path(app/knowledge/provider.py).parents[2] / "knowledge/guidebook/knowledgepack.v1.json"`, i.e.
  relative to the deployed source tree — no cwd dependency. Never add `knowledge/**` or
  `contracts/**` to `excludeFiles`. `SOSU_KNOWLEDGE_PATH` can override it.
  A missing pack is non-fatal (prompts carry "knowledge_version none"), so **verify after deploy**:
  `GET /api/v1/features` must report `knowledge_version: "gb2-5edea367"` (not `none`).
- Live smoke latencies (29 s diagnosis, 47 s prescription, 4 calls) fit comfortably in 200 s.
- **Stage timeouts vs deadline (RD-6, docs/RD6_TIMEOUT.md):** code defaults observe 60 /
  synthesis 90 / repair 40 s (sum 190) are *upper bounds*; every model call is capped at
  `remaining request budget − margin(2 s)` and refused with `MODEL_TIMEOUT` when < 3 s is left, so
  the 180 s deadline always answers first with a structured 504 envelope. Vercel production sets no
  `GEMINI_TIMEOUT_*` env, so the code defaults apply there. The 180 s clock starts at
  `service.run` (after multipart parsing + image normalization); cold start, upload and
  normalization come out of the 20 s margin.
- **Integrity check 2026-10-18 14:52 KST (GET only):** `GET https://sosu-py.vercel.app/api/v1/features`
  → `knowledge_version: "gb2-5edea367"`, `build: "f5680aa4f5ea"` (= HEAD f5680aa),
  `inference.enabled: false (public_inference_disabled)`. `excludeFiles` does not touch
  `knowledge/**` or `contracts/**`.

## Python / dependencies

- `pyproject.toml` `requires-python = ">=3.12"`, `uv.lock` resolves for 3.12+ (local venv 3.12.3).
  `uv.lock` also carries markers for 3.14/3.15. **Which Python version Vercel picks is not
  verified** (no `.python-version` pin). Recommendation (outside Agent B ownership): add
  `.python-version` = `3.12` to remove the ambiguity.
- `[tool.uv] package = false` — app is not installed as a package; Vercel is expected to install
  dependencies from pyproject/uv.lock (not verified) and runs from the source tree, which is why the pack path above works.

## Environment (Vercel project settings, not in repo)

`GEMINI_API_KEY` (secret), optional `GEMINI_MODEL_*` (default `gemini-3.8-flash`, confirmed listed
2026-10-18), `SOSU_ENV=production`, `SOSU_CORS_ORIGINS`, and `SOSU_PUBLIC_INFERENCE_ENABLED=true`
only when paid inference should be public (otherwise the inference gate returns 503).
