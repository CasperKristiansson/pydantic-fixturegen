"""Example Settings model consumed by FastAPI dependency overrides."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ObservabilityConfig(BaseModel):
    tracing_endpoint: str = Field(default="http://localhost:4318")
    sample_rate: float = Field(default=0.2, ge=0, le=1)


class Settings(BaseModel):
    environment: str = Field(default="local", pattern=r"^[a-z]+$")
    region: str = Field(default="eu-north-1")
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    feature_flags: dict[str, bool] = Field(default_factory=lambda: {"delegated_payments": True})


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once for dependency injection."""

    return Settings()
