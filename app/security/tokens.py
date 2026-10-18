"""Report delivery tokens: `<issued_at_unix>.<hex HMAC-SHA256>`.

The MAC covers canonical JSON of {kind, request_id, data, issued_at}. `data` is always the
pydantic `model_dump(mode="json")` of the validated report, so a client echo that reformats
numbers or key order still verifies, while any content change does not.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from app.config import Settings

_FUTURE_SKEW_SECONDS = 300


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _mac(secret: str, kind: str, request_id: str, data: dict[str, Any], issued_at: int) -> str:
    msg = canonical_json(
        {"kind": kind, "request_id": request_id, "data": data, "issued_at": issued_at}
    )
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def sign_report(
    settings: Settings,
    kind: str,
    request_id: str,
    data: dict[str, Any],
    *,
    now: int | None = None,
) -> str | None:
    secret = settings.sosu_delivery_signing_secret.get_secret_value().strip()
    if not secret:
        return None
    issued_at = int(now if now is not None else time.time())
    return f"{issued_at}.{_mac(secret, kind, request_id, data, issued_at)}"


def verify_report(
    settings: Settings,
    token: str,
    kind: str,
    request_id: str,
    data: dict[str, Any],
    *,
    now: int | None = None,
) -> str | None:
    """Return None when valid, else a short machine reason (never the secret or the MAC)."""
    secret = settings.sosu_delivery_signing_secret.get_secret_value().strip()
    if not secret:
        return "signing_secret_not_configured"
    issued_raw, sep, mac = token.partition(".")
    if not sep or not issued_raw.isdigit() or len(mac) != 64:
        return "malformed_token"
    issued_at = int(issued_raw)
    current = int(now if now is not None else time.time())
    if issued_at > current + _FUTURE_SKEW_SECONDS:
        return "token_from_future"
    if current - issued_at > settings.sosu_delivery_token_max_age_seconds:
        return "token_expired"
    expected = _mac(secret, kind, request_id, data, issued_at)
    if not hmac.compare_digest(expected, mac.lower()):
        return "signature_mismatch"
    return None


# ---- Guidebook e-book links: `<expires_at_unix>.<hex HMAC-SHA256("guidebook|<expires_at>")>` ----


def _guidebook_mac(secret: str, expires_at: int) -> str:
    return hmac.new(
        secret.encode("utf-8"), f"guidebook|{expires_at}".encode(), hashlib.sha256
    ).hexdigest()


def sign_guidebook_link(settings: Settings, *, now: int | None = None) -> str | None:
    secret = settings.sosu_delivery_signing_secret.get_secret_value().strip()
    if not secret:
        return None
    expires_at = int(now if now is not None else time.time())
    expires_at += settings.sosu_guidebook_link_max_age_seconds
    return f"{expires_at}.{_guidebook_mac(secret, expires_at)}"


def verify_guidebook_link(settings: Settings, token: str, *, now: int | None = None) -> str | None:
    """Return None when valid, else a short machine reason."""
    secret = settings.sosu_delivery_signing_secret.get_secret_value().strip()
    if not secret:
        return "signing_secret_not_configured"
    expires_raw, sep, mac = token.partition(".")
    if not sep or not expires_raw.isdigit() or len(mac) != 64:
        return "malformed_token"
    expires_at = int(expires_raw)
    if int(now if now is not None else time.time()) > expires_at:
        return "token_expired"
    if not hmac.compare_digest(_guidebook_mac(secret, expires_at), mac.lower()):
        return "signature_mismatch"
    return None
