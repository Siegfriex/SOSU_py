# Image storage — DISABLED (design only)

`GET /api/v1/features` → `image_storage.enabled=false`. Uploaded images are processed in memory
for one request and never persisted. Nothing in this repo writes images anywhere.

## Why disabled
- No verified **private** Vercel Blob store configuration (we have no Blob/API access; public
  Blob URLs are unguessable but not private).
- No consent UX and no consent record (who agreed, to what, when, which version of the notice).
- No retention decision from the owner (`SOSU_IMAGE_RETENTION_DAYS` defaults to 0 = do not store).
- Insight screenshots can contain account names, follower counts and other personal data.

## Requirements before enabling
1. **Consent**: explicit opt-in checkbox (default off), separate from the service ToS, stating
   purpose (service improvement / re-delivery), retention period, and how to delete. Store
   `{consent_version, granted_at, request_id}` with the object metadata.
2. **Private storage**: Vercel Blob with private access (signed, short-lived download URLs) or
   another private bucket; object keys random (`uuid4`), never derived from user data. Server-side
   only; the token (`BLOB_READ_WRITE_TOKEN`) never reaches the client.
3. **Claim token**: response returns an opaque, HMAC-signed claim token (same mechanism as
   `delivery_token`) that authorizes the user to view/delete their own objects; no listing API.
4. **Retention**: `SOSU_IMAGE_RETENTION_DAYS` (> 0 to enable); a scheduled job (Vercel Cron)
   deletes expired objects and logs counts only.
5. **Deletion**: `DELETE /api/v1/images/{claim}` deletes immediately; deletion must also be
   possible by the operator on request.
6. Feature flag stays fail-closed on public runtime until 1–5 are verified, mirroring the
   inference and e-mail gates.
