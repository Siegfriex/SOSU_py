# Report e-mail (Resend) — fail-closed

## Flow
1. `POST /api/v1/diagnosis|prescription` success envelope carries `delivery_token`
   (`"<issued_at_unix>.<hmac hex>"`, or `null` when `SOSU_DELIVERY_SIGNING_SECRET` is unset).
2. Client calls `POST /api/v1/report-email` with JSON
   `{kind, report: <envelope.data>, request_id: <envelope.request_id>, delivery_token, email}`
   (extra fields are rejected — no client free-text body).
3. Server: enabled? (else 503 `SERVICE_UNAVAILABLE`) → strict e-mail regex (no `email-validator`
   dependency installed) → validate `report` against `DiagnosisReportV1`/`PrescriptionReportV1`
   → re-dump canonically and verify HMAC + age ≤ `SOSU_DELIVERY_TOKEN_MAX_AGE_SECONDS` (86400)
   → else 422 `INVALID_REQUEST` (`details[0].reason`: `signature_mismatch`, `token_expired`,
   `malformed_token`, `report_schema`, …).
4. Idempotency key = `sha256(token + "|" + lower(email))`. Per-instance in-memory cache returns
   `{"status":"duplicate"}`; the same key is sent as Resend `Idempotency-Key`, which dedupes across
   instances for 24h on Resend's side.
5. Server renders Korean plain text + escaped HTML from the verified report
   (`app/email/render.py`) and sends via `ResendProvider` (`POST https://api.resend.com/emails`).
   Provider failure → 502 `EMAIL_DELIVERY_FAILED` (`retryable=true`, not cached).

## Configuration
`RESEND_API_KEY`, `SOSU_EMAIL_FROM` (Resend-verified domain), `SOSU_DELIVERY_SIGNING_SECRET`
(≥ 32 random bytes); on Vercel/production additionally `SOSU_PUBLIC_EMAIL_ENABLED=true`.
Per-instance limit `SOSU_RATELIMIT_EMAIL_PER_MINUTE` is a backstop only — put the e-mail route in
the Vercel WAF rate-limit rule as well.

## Guidebook e-book link
When `SOSU_GUIDEBOOK_URL` (secret; the PDF lives outside the repo, e.g. Vercel Blob) and the signing
secret are set, every report e-mail gets a "가이드북 PDF 받기" block linking to
`{SOSU_PUBLIC_API_BASE_URL}/api/v1/guidebook?t=<expires_at>.<hmac>`. Valid → 302 to the storage URL
(`no-store`, `no-referrer`); expired/invalid → 410 page; unconfigured → 404 page. The storage URL is
never in the e-mail, the features probe or a page. Validity `SOSU_GUIDEBOOK_LINK_MAX_AGE_SECONDS`
(default 7 days). `/api/v1/features` reports `guidebook.enabled`. Owner walkthrough:
`docs/EMAIL_SETUP_GUIDE.md`; status: `python3 scripts/check_email_setup.py`.

## Residual risks
- A holder of a valid token can send the report to any address for 24h (the report is the user's
  own content; no free text). Shorten max age if needed.
- Rotating the signing secret invalidates all outstanding tokens (acceptable).
- Tests use a fake provider; no real e-mail has been sent from this codebase.
- The guidebook redirect reveals the storage URL to the recipient's browser; storage URLs are
  unguessable but not access-controlled.
