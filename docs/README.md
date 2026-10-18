# docs

| Note | Topic |
|---|---|
| [SECURITY.md](SECURITY.md) | public-runtime gate, body cap, rate limiting, secrets handling |
| [VERCEL.md](VERCEL.md) | deployment, env vars, function limits |
| [RD6_TIMEOUT.md](RD6_TIMEOUT.md) | request deadline budget (180 s) and per-stage timeouts |
| [RD5_GROUNDING.md](RD5_GROUNDING.md) | prescription grounding: root cause, evidence boundary, validator checks, residual risks |
| [KNOWLEDGE.md](KNOWLEDGE.md) | guidebook KnowledgePack: format, injection, versioning |
| [RESEARCH_BOUNDARY.md](RESEARCH_BOUNDARY.md) | external research interface (disabled) |
| [EMAIL.md](EMAIL.md) | report email delivery and guidebook e-book link (implemented, off until configured) |
| [EMAIL_SETUP_GUIDE.md](EMAIL_SETUP_GUIDE.md) | 이메일 켜기: 처음 하는 사람용 단계별 가이드 (Resend · Blob · env · WAF) |
| [IMAGE_STORAGE.md](IMAGE_STORAGE.md) | consent-based image retention design (not implemented) |
| [LIVE_SMOKE.md](LIVE_SMOKE.md) | capped live Gemini smoke runs and their quality notes |
| [AUDIT_2026-09-13.md](AUDIT_2026-09-13.md) | historical audit before integration |

- `../SSOT/` holds the product and inference SSOT (owner-provided).
- The API contract of record is `../contracts/openapi.json` + `../contracts/fixtures/*`. Where the SSOT and contract V1 disagree on field names or enum values, contract V1 wins.
