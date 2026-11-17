"""Configuration management for InsightBot using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """InsightBot application settings, loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_prefix="INSIGHTBOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    env: Literal["development", "test", "production"] = "development"

    # HTTP Server
    host: str = "127.0.0.1"
    port: int = 8000

    # MongoDB
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db: str = "insightbot"
    mongo_timeout_ms: int = 5000

    # Authentication & Secrets
    secret_key: str = Field(
        default="",
        description="Cryptographic secret key for session and token signing",
    )
    secret_file: Optional[Path] = None

    # Storage Paths
    raw_storage_path: Path = Path("data/raw")
    export_storage_path: Path = Path("data/exports")
    sources_config_path: Path = Path("configs/sources.yaml")
    model_manifest_path: Path = Path("models/manifest.json")
    static_dir: Optional[Path] = Path("apps/web/dist")

    # Timezone & Localization
    timezone: str = "UTC"

    # Search and ML feature toggles
    search_backend: Literal["basic", "opensearch"] = "basic"
    enable_llm: bool = False

    # External local services
    prefect_api_url: Optional[str] = Field(
        default=None,
        validation_alias="PREFECT_API_URL",
    )
    hf_hub_offline: str = Field(
        default="1",
        validation_alias="HF_HUB_OFFLINE",
    )

    @field_validator("secret_key", mode="after")
    @classmethod
    def resolve_secret_key(cls, v: str, info: object) -> str:
        """Resolve secret key from secret_file if secret_key is not set."""
        if v:
            return v
        return ""

    def validate_runtime(self) -> list[str]:
        """Validate operational readiness and return a list of issue descriptions."""
        issues: list[str] = []

        if self.env == "production" and (not self.secret_key or len(self.secret_key) < 32):
            issues.append(
                "INSIGHTBOT_SECRET_KEY must be set with at least 32 characters in production."
            )

        try:
            self.raw_storage_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            issues.append(
                f"Cannot access or create raw storage directory '{self.raw_storage_path}': {e}"
            )

        try:
            self.export_storage_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            issues.append(
                f"Cannot access or create export storage directory '{self.export_storage_path}': {e}"
            )

        return issues


@lru_cache()
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()
