"""Runtime posture: are we publicly deployed, and which paid/side-effecting features are open?

Fail-closed rule: on Vercel (`VERCEL=1`) or `SOSU_ENV=production`, public Gemini inference and
report e-mail stay OFF until the owner explicitly opens them via env (docs/SECURITY.md).
"""

from __future__ import annotations

import os

from app.config import Settings

# Any of these means "deployed on Vercel / a serverless host". Checked broadly on purpose: the
# `VERCEL*` system vars depend on a project toggle, `AWS_LAMBDA_FUNCTION_NAME` does not. A false
# positive only closes features (fail-closed); a false negative would open paid inference.
PUBLIC_RUNTIME_ENV_MARKERS = (
    "VERCEL",
    "VERCEL_ENV",
    "VERCEL_URL",
    "VERCEL_REGION",
    "AWS_LAMBDA_FUNCTION_NAME",
)


def is_public_runtime(settings: Settings) -> bool:
    if settings.sosu_env == "production":
        return True
    return any(os.getenv(name, "").strip() for name in PUBLIC_RUNTIME_ENV_MARKERS)


def build_sha() -> str | None:
    sha = os.getenv("VERCEL_GIT_COMMIT_SHA", "").strip()[:12]
    return sha or None


def inference_status(settings: Settings) -> tuple[bool, str | None]:
    if is_public_runtime(settings) and not settings.sosu_public_inference_enabled:
        return False, "public_inference_disabled"
    if is_public_runtime(settings) and not settings.gemini_configured:
        return False, "gemini_not_configured"
    return True, None


def delivery_signing_configured(settings: Settings) -> bool:
    return bool(settings.sosu_delivery_signing_secret.get_secret_value().strip())


def email_status(settings: Settings) -> tuple[bool, str | None]:
    if not settings.resend_api_key.get_secret_value().strip():
        return False, "resend_not_configured"
    if not settings.sosu_email_from.strip():
        return False, "sender_not_configured"
    if not delivery_signing_configured(settings):
        return False, "signing_secret_not_configured"
    if is_public_runtime(settings) and not settings.sosu_public_email_enabled:
        return False, "public_email_disabled"
    return True, None
