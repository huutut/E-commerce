from functools import lru_cache
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Commerce Platform"
    app_env: str = "local"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    admin_session_secret: str = "change-me-local-admin-secret"
    admin_session_ttl_seconds: int = 60 * 60 * 8
    admin_cookie_secure: bool = False
    admin_cookie_samesite: str = "lax"
    api_rate_limit_requests: int = 120
    api_rate_limit_window_seconds: int = 60
    upload_dir: str = "uploads"
    upload_max_bytes: int = 2 * 1024 * 1024
    public_base_url: str = "http://127.0.0.1:8000"
    payment_provider: str = "mock"
    payment_live_mode: bool = False
    payment_webhook_secret: str = "local-webhook-secret-change-me"
    shipping_provider: str = "manual"
    shipping_tracking_base_url: str = "https://www.baidu.com/s?wd="
    ops_metrics_token: str = ""

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/commerce"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("admin_cookie_samesite")
    @classmethod
    def validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("admin_cookie_samesite must be lax, strict, or none")
        return normalized

    @model_validator(mode="after")
    def validate_admin_secret(self) -> Self:
        is_local = self.app_env.lower() in {"local", "dev", "development", "test"}
        default_secret = self.admin_session_secret == "change-me-local-admin-secret"
        if not is_local and (default_secret or len(self.admin_session_secret) < 32):
            raise ValueError("Set a strong ADMIN_SESSION_SECRET outside local development.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
