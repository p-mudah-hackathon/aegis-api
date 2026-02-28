"""
Application configuration — validates env vars at startup via Pydantic BaseSettings.
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """All configuration from environment variables."""

    # ── Alibaba DashScope (Qwen AI) ──────────────────────────────────────
    dashscope_api_key: str = Field(
        default="",
        description="DashScope API key for Qwen 3.5 Plus fraud reasoning",
    )

    # ── aegis-ai ML model service ────────────────────────────────────────
    aegis_ai_url: str = Field(
        default="http://localhost:8000",
        description="Base URL of the aegis-ai ML model service",
    )

    # ── Database (Supabase PostgreSQL) ───────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/postgres",
        description="Async SQLAlchemy database URL (PostgreSQL + asyncpg)",
    )

    # ── Paylabs Integrations ─────────────────────────────────────────────
    paylabs_merchant_id: str = Field(
        default="",
        description="Paylabs Merchant ID",
    )
    paylabs_public_key: str = Field(
        default="",
        description="Paylabs Public Key",
    )
    paylabs_private_key: str = Field(
        default="",
        description="Paylabs Private Key",
    )

    # ── Server ───────────────────────────────────────────────────────────
    app_name: str = "AegisNode API Gateway"
    debug: bool = False
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton — import this everywhere
settings = Settings()
