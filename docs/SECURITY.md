# SOSU_py — Security posture (Phase 2)

## Why fail-closed
The Vercel deployment (`sosu-py`) previously exposed paid Gemini inference publicly with no rate
limit. This codebase has no verified access to Vercel env vars, firewall, KV or Blob, so **no
shared rate limit can be verified from code**. Therefore paid inference is closed by default on
any public runtime and only the owner can open it.

## Enforced in code
| Control | Where | Behaviour |
|---|---|---|
| Inference gate | `app/security/middleware.py` (pure ASGI, runs before body parsing) | On Vercel (any of `VERCEL`, `VERCEL_ENV`, `VERCEL_URL`, `VERCEL_REGION`, `AWS_LAMBDA_FUNCTION_NAME` set) or `SOSU_ENV=production`: `POST /api/v1/diagnosis` and `/prescription` return **503 `SERVICE_UNAVAILABLE`** (`retryable=false`, `details[0].reason`) unless `SOSU_PUBLIC_INFERENCE_ENABLED=true`. No image is read, no Gemini call is made. Local dev/test unchanged. |
| Body size cap | same middleware | `Content-Length > SOSU_MAX_REQUEST_BYTES` (4,000,000) → 413 `IMAGE_TOO_LARGE`. Without Content-Length the body is counted while streaming and rejected at the cap. Applies to all POST/PUT/PATCH. |
| Per-instance limiter | `app/security/ratelimit.py` | Token bucket per client IP (`x-forwarded-for` first hop) on public runtime only: AI `SOSU_RATELIMIT_AI_PER_MINUTE` (6), e-mail `SOSU_RATELIMIT_EMAIL_PER_MINUTE` (3) → 429 `RATE_LIMITED`. **NOT a shared limit**: each Vercel instance has its own memory; this is only a backstop. |
| E-mail fail-closed | `app/security/runtime.py::email_status` | Needs `RESEND_API_KEY` + `SOSU_EMAIL_FROM` + `SOSU_DELIVERY_SIGNING_SECRET`, and on public runtime also `SOSU_PUBLIC_EMAIL_ENABLED=true`; else 503. |
| Report integrity | `app/security/tokens.py` | `delivery_token = "<issued_at>.<HMAC-SHA256>"` over canonical JSON `{kind, request_id, data, issued_at}`; 24h max age; constant-time compare. E-mail body is rendered server-side from the verified report only. |
| Build provenance | middleware + `GET /api/v1/features` | `X-SOSU-Build` header = `VERCEL_GIT_COMMIT_SHA[:12]` so anyone can verify which commit is live. |
| Logging | middleware / delivery | Only `request_id`, path, error code. Never request bodies, images, e-mail addresses, IPs, keys. Secrets are `SecretStr`. |
| CORS | `app/config.py` | Default `http://localhost:5173,https://sosu-rosy.vercel.app`; env `SOSU_CORS_ORIGINS` overrides. CORS wraps rejections so the web can read 413/429/503. |

`GET /api/v1/features` reports `inference.enabled/reason`, `email.enabled/reason`,
`image_storage.enabled=false`, `research`, `knowledge_version`, `build`.

## Owner actions (required to open production) — in this order
1. **Vercel Firewall → WAF custom rule, rate limit** on paths `/api/v1/diagnosis`, `/api/v1/prescription`, `/api/v1/report-email` (e.g. fixed window 60 s, ≤ 5 req per IP, action deny/429), plus Attack Challenge Mode on abuse.
2. **Spend limits**: Google AI Studio / Cloud billing budget + alert on the Gemini key; Vercel Spend Management on the project.
3. Set `SOSU_PUBLIC_INFERENCE_ENABLED=true` in Vercel Production env and redeploy. Verify `GET https://sosu-py.vercel.app/api/v1/features` → `inference.enabled=true` and `X-SOSU-Build` = expected SHA.
4. E-mail (optional): verify a sending domain in Resend; set `RESEND_API_KEY`, `SOSU_EMAIL_FROM` (on that domain), `SOSU_DELIVERY_SIGNING_SECRET` (`openssl rand -hex 32`), then `SOSU_PUBLIC_EMAIL_ENABLED=true`.
5. `SOSU_CORS_ORIGINS=https://sosu-rosy.vercel.app` (plus any preview origins you want).
6. Rotate the Gemini key that was exposed while production was open, if any abuse is visible in usage.

Until step 3 the production frontend must show the "서비스 일시 중단" state (driven by
`/api/v1/features` or the 503 envelope).
