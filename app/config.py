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

    # Timeout hierarchy (seconds). Stages must fit inside the overall request deadline.
    gemini_timeout_observe: float = 45.0
    gemini_timeout_synthesis: float = 90.0
    gemini_timeout_repair: float = 40.0
    sosu_request_deadline_seconds: float = 180.0

    sosu_env: Literal["development", "test", "production"] = "development"
    sosu_log_level: str = "INFO"
    sosu_cors_origins: str = "http://localhost:5173"
    sosu_api_host: str = "127.0.0.1"
    sosu_api_port: int = 8000

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
