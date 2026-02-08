"""Threshold and config endpoints."""
from fastapi import APIRouter, Depends

from app.config import get_settings
from app.schemas import SettingsResponse, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings_endpoint():
    """Return current config (from env/config)."""
    s = get_settings()
    return SettingsResponse(
        min_spend=s.min_spend,
        min_purchases=s.min_purchases,
        min_age_days=s.min_age_days,
        winner_threshold=s.winner_threshold,
        loser_threshold=s.loser_threshold,
        improving_slope=s.improving_slope,
        declining_slope=s.declining_slope,
        volatile_cpa_std=s.volatile_cpa_std,
        roas_weight=s.roas_weight,
        spend_weight=s.spend_weight,
        cvr_weight=s.cvr_weight,
        volume_weight=s.volume_weight,
        max_scale_pct=s.max_scale_pct,
        scale_cooldown_hours=s.scale_cooldown_hours,
        max_daily_budget_increase=s.max_daily_budget_increase,
        broad_roas_threshold_multiplier=s.broad_roas_threshold_multiplier,
        broad_min_days_before_pause=s.broad_min_days_before_pause,
        lla_scale_pct_bump=s.lla_scale_pct_bump,
        lla_fatigue_spend_multiplier=s.lla_fatigue_spend_multiplier,
        interest_days_decline_before_pause=s.interest_days_decline_before_pause,
        custom_max_scale_pct=s.custom_max_scale_pct,
    )


@router.patch("", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate):
    """Update config. For now config is env-only; persistence can be added later."""
    raise NotImplementedError("Settings persistence not implemented; use env vars")
