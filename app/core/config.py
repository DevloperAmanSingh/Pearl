from functools import lru_cache
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    github_app_id: Optional[int] = Field(default=None, validation_alias="GITHUB_APP_ID")
    github_app_client_id: Optional[str] = Field(default=None, validation_alias="GITHUB_APP_CLIENT_ID")
    github_app_installation_id: Optional[int] = Field(default=None, validation_alias="GITHUB_APP_INSTALLATION_ID")
    github_app_private_key_path: Optional[str] = Field(default=None, validation_alias="GITHUB_APP_PRIVATE_KEY_PATH")
    github_webhook_secret: Optional[SecretStr] = Field(default=None, validation_alias="GITHUB_WEBHOOK_SECRET")
    github_api_base_url: str = Field(default="https://api.github.com", validation_alias="GITHUB_API_BASE_URL")

    openai_api_key: Optional[SecretStr] = Field(default=None, validation_alias="OPENAI_API_KEY")

    database_url: str = Field(default="postgresql+psycopg://postgres:postgres@localhost:5432/pearl", validation_alias="DATABASE_URL")

    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    celery_task_default_queue: str = Field(default="pr_ingestion", validation_alias="CELERY_TASK_DEFAULT_QUEUE")

    github_event_actions: tuple[str, ...] = ("opened", "synchronize", "ready_for_review","reopened")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
