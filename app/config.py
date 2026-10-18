"""Runtime settings. All Gemini/model configuration comes from env only."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

CONTRACT_VERSION = "1.0"
SERVICE_NAME = "sosu-ai"
API_KEY_PLACEHOLDER = "PASTE_YOUR_GEMINI_API_KEY_HERE"

ThinkingLevel = Literal["minimal", "low", "medium", "high"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: SecretStr = Field(default=SecretStr(""))

    gemini_model_observe: str = "gemini-3.8-flash"
    gemini_model_diagnosis: str = "gemini-3.8-flash"
    gemini_model_prescription: str = "gemini-3.8-flash"

    gemini_thinking_observe: ThinkingLevel = "low"
    gemini_thinking_synthesis: ThinkingLevel = "medium"
    gemini_thinking_repair: ThinkingLevel = "low"

    gemini_max_output_observe: int = 2048
    gemini_max_output_diagnosis: int = 8192
    gemini_max_output_prescription: int = 4096
    gemini_max_output_repair: int = 4096

    # Timeout hierarchy (seconds). Stage timeouts are UPPER BOUNDS: each call is capped at the
    # remaining request budget (app/services/deadline.py budget_spec), so their sum (190) may
    # exceed the deadline; the deadline (180) is always enforced and stays < vercel.json
    # maxDuration (200). RD-6 (docs/RD6_TIMEOUT.md): observe 45 → 60.
    gemini_timeout_observe: float = 60.0
    gemini_timeout_synthesis: float = 90.0
    gemini_timeout_repair: float = 40.0
    sosu_request_deadline_seconds: float = 180.0

    sosu_env: Literal["development", "test", "production"] = "development"
    sosu_log_level: str = "INFO"
    sosu_cors_origins: str = "http://localhost:5173,https://sosu-rosy.vercel.app"
    sosu_api_host: str = "127.0.0.1"
    sosu_api_port: int = 8000

    # Guidebook KnowledgePack JSON. Empty → <repo>/knowledge/guidebook/knowledgepack.v1.json.
    # Missing/invalid file is not fatal: prompts carry a "knowledge_version none" block.
    sosu_knowledge_path: str = ""
    # External research (Phase 2). False → NullResearchProvider ("unavailable"), never fabricated.
    sosu_research_enabled: bool = False

    # ---- Phase 2 security / delivery (see docs/SECURITY.md, docs/EMAIL.md) ----
    # Public paid inference FAILS CLOSED on Vercel / SOSU_ENV=production until the owner has an
    # enforceable shared rate limit (Vercel WAF rule + spend cap) and sets this to true.
    sosu_public_inference_enabled: bool = False
    # Per-instance token buckets (NOT a shared limit — a backstop only). Requests per minute per IP.
    sosu_ratelimit_ai_per_minute: int = 6
    sosu_ratelimit_email_per_minute: int = 3
    sosu_max_request_bytes: int = 4_000_000

    # Report e-mail (Resend). Enabled only when all three are set (and, on Vercel/production,
    # SOSU_PUBLIC_EMAIL_ENABLED=true).
    resend_api_key: SecretStr = Field(default=SecretStr(""))
    sosu_email_from: str = ""
    sosu_delivery_signing_secret: SecretStr = Field(default=SecretStr(""))
    sosu_public_email_enabled: bool = False
    sosu_delivery_token_max_age_seconds: int = 86_400
    # Guidebook e-book (docs/EMAIL.md). The PDF lives OUTSIDE the repo (Vercel Blob or similar);
    # this URL is a secret. Report e-mails carry a signed, expiring link to /api/v1/guidebook,
    # which redirects to it. Empty → no guidebook link in e-mails.
    sosu_guidebook_url: SecretStr = Field(default=SecretStr(""))
    sosu_guidebook_link_max_age_seconds: int = 7 * 86_400
    # Public origin of this API, used to build links in e-mails.
    sosu_public_api_base_url: str = "https://sosu-py.vercel.app"

    # Image storage is intentionally NOT implemented (docs/IMAGE_STORAGE.md).
    sosu_image_retention_days: int = 0

    run_live_gemini_tests: bool = False

    @property
    def gemini_configured(self) -> bool:
        key = self.gemini_api_key.get_secret_value().strip()
        return bool(key) and key != API_KEY_PLACEHOLDER

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.sosu_cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
