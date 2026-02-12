"""Centralized configuration - all thresholds and env settings."""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: str = "development"
    secret_key: str = "dev-secret-change-me"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    # Database
    database_url: str = "sqlite:///./roas.db"

    # Meta
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = "http://localhost:8000/api/auth/meta/callback"
    meta_base_delay_seconds: float = 1.0
    meta_batch_size: int = 20
    meta_max_backoff_seconds: int = 900

    # Anthropic
    anthropic_api_key: str = ""

    # --- Noise filters ---
    min_spend: float = 3000.0  # INR
    min_purchases: int = 2
    min_age_days: int = 2

    # --- Performance buckets (normalized ROAS) ---
    winner_threshold: float = 1.2
    loser_threshold: float = 0.9

    # --- Trend thresholds ---
    improving_slope: float = 0.05
    declining_slope: float = -0.05
    volatile_cpa_std: float = 0.3

    # --- Scoring weights ---
    roas_weight: float = 0.7
    spend_weight: float = 0.15
    cvr_weight: float = 0.05
    volume_weight: float = 0.1

    # --- Guardrails ---
    max_scale_pct: int = 25
    scale_cooldown_hours: int = 48
    max_daily_budget_increase: float = 5000.0  # INR

    # --- Audience-type modifiers (stored as JSON or overridable in DB) ---
    # Broad: lower ROAS threshold, slower pause
    broad_roas_threshold_multiplier: float = 0.9
    broad_min_days_before_pause: int = 5
    # LLA 1%: faster scale, fatigue check
    lla_scale_pct_bump: int = 5  # add to max_scale_pct
    lla_fatigue_spend_multiplier: float = 2.0  # vs median spend
    # Interest: lower patience
    interest_days_decline_before_pause: int = 3
    # Custom: lower scale cap
    custom_max_scale_pct: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()
