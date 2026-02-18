from __future__ import annotations

from enum import StrEnum

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Language(StrEnum):
    PT_BR = "pt-BR"
    EN_US = "en-US"


class ModelProvider(StrEnum):
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    GEMINI = "gemini"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # GitHub App
    github_app_id: str
    github_private_key: str = ""
    github_private_key_path: str = ""
    github_webhook_secret: str

    # Database
    database_url: str = "postgresql+asyncpg://reviewer:reviewer@localhost:5433/louro"

    # Pgvector connection (psycopg format for agno)
    @property
    def pgvector_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg")

    # Model
    model_provider: ModelProvider = ModelProvider.ANTHROPIC
    primary_model_id: str = "claude-sonnet-4-5-20250929"
    standard_model_id: str = "claude-sonnet-4-5-20250929"
    classifier_model_id: str = "claude-haiku-4-5-20251001"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_input_tokens_per_minute: int = 30_000

    # AWS Bedrock
    aws_region: str = "us-east-1"

    # Google Gemini
    google_api_key: str = ""

    # Logging
    log_format: str = "text"  # "text" or "json"
    log_level: str = "INFO"

    # API key for management endpoints (empty = no auth)
    api_key: str = ""

    @model_validator(mode="after")
    def _validate_config(self) -> Settings:
        if not self.github_private_key and not self.github_private_key_path:
            raise ValueError("Set GITHUB_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH")
        if self.model_provider == ModelProvider.ANTHROPIC and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when model_provider is 'anthropic'")
        if self.model_provider == ModelProvider.GEMINI and not self.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when model_provider is 'gemini'")
        return self

    def get_github_private_key_bytes(self) -> bytes:
        if self.github_private_key:
            return self.github_private_key.encode()
        if self.github_private_key_path:
            with open(self.github_private_key_path, "rb") as f:
                return f.read()
        raise ValueError("Set GITHUB_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH")


settings: Settings | None = None


def get_settings() -> Settings:
    global settings
    if settings is None:
        settings = Settings()  # type: ignore[call-arg]
    return settings


def override_settings(s: Settings) -> None:
    global settings
    settings = s


def reset_settings() -> None:
    global settings
    settings = None
