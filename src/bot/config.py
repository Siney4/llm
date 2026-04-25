"""Environment-backed configuration."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")

    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")

    openai_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["gpt-4o", "gpt-4o-mini"],
        alias="OPENAI_MODELS",
    )
    anthropic_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"],
        alias="ANTHROPIC_MODELS",
    )

    default_provider: str = Field("openai", alias="DEFAULT_PROVIDER")
    system_prompt: str = Field(
        "You are a helpful, concise assistant. Answer in the user's language.",
        alias="SYSTEM_PROMPT",
    )

    max_history_messages: int = Field(30, alias="MAX_HISTORY_MESSAGES")
    max_output_tokens: int = Field(2048, alias="MAX_OUTPUT_TOKENS")

    db_path: str = Field("data/bot.db", alias="DB_PATH")

    allowed_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ALLOWED_USER_IDS"
    )
    admin_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ADMIN_USER_IDS"
    )

    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator("openai_models", "anthropic_models", mode="before")
    @classmethod
    def _split_models(cls, v: object) -> object:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("allowed_user_ids", "admin_user_ids", mode="before")
    @classmethod
    def _split_ids(cls, v: object) -> object:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("default_provider")
    @classmethod
    def _check_provider(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"openai", "anthropic"}:
            raise ValueError("DEFAULT_PROVIDER must be 'openai' or 'anthropic'")
        return v

    def has_openai(self) -> bool:
        return bool(self.openai_api_key and self.openai_models)

    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_models)


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
