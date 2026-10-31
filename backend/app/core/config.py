"""Environment-based application settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_mode: Literal["sqlserver", "sqlite"] = "sqlserver"
    database_url: SecretStr | None = None
    sqlite_database_path: str = "storage/ledgerpilot-demo.sqlite3"
    jwt_secret_key: SecretStr
    access_token_minutes: int = 30
    document_storage_root: str = "storage/uploads"
    max_document_upload_mb: int = 20
    ai_provider: str = "none"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: SecretStr | None = None
    ai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 characters")
        return value

    @model_validator(mode="after")
    def validate_database_configuration(self):
        if self.database_mode == "sqlserver" and self.database_url is None:
            raise ValueError("DATABASE_URL is required when DATABASE_MODE=sqlserver")
        if self.database_mode == "sqlite" and not self.sqlite_database_path.strip():
            raise ValueError("SQLITE_DATABASE_PATH cannot be empty")
        return self

    @property
    def resolved_sqlite_path(self) -> Path:
        path = Path(self.sqlite_database_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
