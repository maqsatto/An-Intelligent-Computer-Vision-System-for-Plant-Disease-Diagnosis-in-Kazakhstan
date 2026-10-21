from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGRO_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(default="postgresql+psycopg://localhost/agrovision", repr=False)
    environment: str = "production"
    dev_predictor: bool = False
    dev_token_secret: str = Field(default="", repr=False)
    download_secret: str = Field(default="", repr=False)
    storage_dir: Path = Path("storage/photos")
    bundle_dir: Path = Path("artifacts/active")
    research_bundle_dir: Path | None = None
    oidc_issuer: str = ""
    oidc_audience: str = "agrovision-mobile"
    oidc_jwks_url: str = ""
    max_image_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    max_image_pixels: int = Field(default=20_000_000, ge=1, le=20_000_000)
    max_attempts: int = Field(default=3, ge=1, le=10)
    lease_seconds: float = Field(default=60, gt=0, le=3600)
    inference_timeout_seconds: float = Field(default=30, gt=0, le=1800)
    retry_base_seconds: float = 2
    download_ttl_seconds: int = Field(default=120, ge=1, le=600)

    @field_validator("research_bundle_dir", mode="before")
    @classmethod
    def empty_research_path(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_environment(self):
        if self.environment not in {"production", "development", "test"}:
            raise ValueError("environment must be production, development or test")
        if self.environment == "production" and (
            self.dev_predictor or self.dev_token_secret or self.research_bundle_dir
        ):
            raise ValueError("Production refuses development predictor and development credentials")
        if len(self.download_secret) < 32:
            raise ValueError("download_secret must contain at least 32 random characters")
        if self.environment != "production" and len(self.dev_token_secret) < 32:
            raise ValueError("development token secret must contain at least 32 random characters")
        if self.environment == "production" and not (
            self.oidc_issuer.startswith("https://") and self.oidc_jwks_url.startswith("https://")
        ):
            raise ValueError("Production requires HTTPS OIDC issuer and JWKS URL")
        if not 0 < self.inference_timeout_seconds < self.lease_seconds:
            raise ValueError("lease must exceed bounded inference timeout")
        if self.max_attempts < 1 or self.retry_base_seconds < 0:
            raise ValueError("invalid retry configuration")
        return self


@lru_cache
def get_settings():
    return Settings()
