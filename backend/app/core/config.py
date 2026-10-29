from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")
    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://nexora:replace_with_your_unique_password@localhost:55432/nexora"
    )
    redis_url: SecretStr = SecretStr("redis://localhost:56379/0")
    allowed_origins: list[str] = ["http://localhost:3000"]

    ocr_url: str = ""
    ocr_api_key: SecretStr = SecretStr("")
    ai_provider: Literal["compatible", "ollama"] = "compatible"
    ai_request_timeout: int = Field(default=30, ge=5, le=180)
    ai_base_url: str = ""
    ai_api_key: SecretStr = SecretStr("")
    ai_chat_model: str = ""
    ai_embedding_model: str = ""
    document_chunk_size: int = 1200
    document_chunk_overlap: int = 150

    @field_validator("ai_base_url", "ocr_url")
    @classmethod
    def provider_url(cls, value):
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("AI_BASE_URL must be an HTTP(S) endpoint")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def explicit_origins(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("Explicit origins are required")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
