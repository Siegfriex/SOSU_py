"""E-mail provider abstraction. Real sends go through SmtpProvider (Gmail) or ResendProvider;
tests use fakes."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid, parseaddr
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


class SmtpProvider:
    """Gmail SMTP (implicit TLS, port 465) with an App Password. No domain needed; Gmail caps a
    personal account at roughly 500 recipients/day. The From address must be the Gmail account
    (Gmail rewrites any other From). There is no provider-side idempotency key, so duplicate
    protection is the per-instance cache in app/api/delivery.py only."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        *,
        timeout: float = 15.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._timeout = timeout

    def _build(self, message: EmailMessage) -> MimeMessage:
        name, addr = parseaddr(self._sender)
        mime = MimeMessage()
        mime["From"] = formataddr((name, addr or self._username))
        mime["To"] = message.to
        mime["Subject"] = message.subject
        domain = (addr or self._username).rpartition("@")[2] or None
        mime["Message-ID"] = make_msgid(idstring=message.idempotency_key[:16], domain=domain)
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")
        return mime

    def _send_sync(self, mime: MimeMessage) -> None:
        context = ssl.create_default_context()
        if self._port == 465:
            with smtplib.SMTP_SSL(
                self._host, self._port, timeout=self._timeout, context=context
            ) as smtp:
                smtp.login(self._username, self._password)
                smtp.send_message(mime)
        else:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.starttls(context=context)
                smtp.login(self._username, self._password)
                smtp.send_message(mime)

    async def send(self, message: EmailMessage) -> None:
        mime = self._build(message)
        try:
            await asyncio.to_thread(self._send_sync, mime)
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailDeliveryError(f"smtp auth failed: {exc.smtp_code}") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailDeliveryError(f"smtp error: {type(exc).__name__}") from exc


def build_provider(settings: Settings) -> EmailProvider:
    sender = settings.sosu_email_from.strip()
    if not sender:
        return NullProvider()
    if settings.smtp_configured:
        return SmtpProvider(
            settings.sosu_smtp_host.strip(),
            settings.sosu_smtp_port,
            settings.sosu_smtp_username.strip(),
            # Google shows App Passwords as "abcd efgh ijkl mnop"; spaces are not part of it.
            settings.sosu_smtp_password.get_secret_value().replace(" ", "").strip(),
            sender,
        )
    key = settings.resend_api_key.get_secret_value().strip()
    if key:
        return ResendProvider(key, sender)
    return NullProvider()


def get_email_provider() -> EmailProvider:
    """FastAPI dependency; override via app.dependency_overrides in tests."""
    return build_provider(get_settings())
