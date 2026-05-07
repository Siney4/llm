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

    openai_base_url: str = Field("http://localhost:8080/v1", alias="OPENAI_BASE_URL")
    openai_api_key: str = Field("sk-no-key-required", alias="OPENAI_API_KEY")
    openai_model: str = Field("Qwen2.5-14B-Instruct-Q4_K_M", alias="OPENAI_MODEL")

    llm_temperature: float = Field(0.7, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(900, alias="LLM_MAX_TOKENS")
    llm_timeout_s: float = Field(120.0, alias="LLM_TIMEOUT_S")

    buffer_fraction: float = Field(0.15, alias="BUFFER_FRACTION")

    db_path: str = Field("data/nutrition.db", alias="DB_PATH")

    allowed_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ALLOWED_USER_IDS"
    )

    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def _split_ids(cls, v: object) -> object:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("buffer_fraction")
    @classmethod
    def _check_buffer(cls, v: float) -> float:
        if not (0.0 <= v <= 0.4):
            raise ValueError("BUFFER_FRACTION must be in [0.0, 0.4]")
        return v


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
