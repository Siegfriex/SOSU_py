"""E-mail provider abstraction. Real sends only through ResendProvider; tests use fakes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings, get_settings

RESEND_URL = "https://api.resend.com/emails"


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str
    idempotency_key: str


class EmailDeliveryError(Exception):
    """Provider rejected or failed. Message is internal only — never forwarded to the client."""


class EmailProvider(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class NullProvider:
    """Used when e-mail is not configured. Always refuses; never sends anything."""

    async def send(self, message: EmailMessage) -> None:
        raise EmailDeliveryError("email provider not configured")


class ResendProvider:
    def __init__(self, api_key: str, sender: str, *, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._sender = sender
        self._timeout = timeout

    async def send(self, message: EmailMessage) -> None:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": message.idempotency_key,
        }
        body = {
            "from": self._sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
            "html": message.html,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(RESEND_URL, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise EmailDeliveryError(f"transport error: {type(exc).__name__}") from exc
        if resp.status_code >= 300:
            raise EmailDeliveryError(f"resend status {resp.status_code}")


def build_provider(settings: Settings) -> EmailProvider:
    key = settings.resend_api_key.get_secret_value().strip()
    sender = settings.sosu_email_from.strip()
    if key and sender:
        return ResendProvider(key, sender)
    return NullProvider()


def get_email_provider() -> EmailProvider:
    """FastAPI dependency; override via app.dependency_overrides in tests."""
    return build_provider(get_settings())
