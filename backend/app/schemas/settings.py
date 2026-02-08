from pydantic import BaseModel


class SettingsResponse(BaseModel):
    min_spend: float
    min_purchases: int
    min_age_days: int
    winner_threshold: float
    loser_threshold: float
    improving_slope: float
    declining_slope: float
    volatile_cpa_std: float
    roas_weight: float
    spend_weight: float
    cvr_weight: float
    volume_weight: float
    max_scale_pct: int
    scale_cooldown_hours: int
    max_daily_budget_increase: float
    broad_roas_threshold_multiplier: float
    broad_min_days_before_pause: int
    lla_scale_pct_bump: int
    lla_fatigue_spend_multiplier: float
    interest_days_decline_before_pause: int
    custom_max_scale_pct: int


class SettingsUpdate(BaseModel):
    min_spend: float | None = None
    min_purchases: int | None = None
    min_age_days: int | None = None
    winner_threshold: float | None = None
    loser_threshold: float | None = None
    improving_slope: float | None = None
    declining_slope: float | None = None
    volatile_cpa_std: float | None = None
    roas_weight: float | None = None
    spend_weight: float | None = None
    cvr_weight: float | None = None
    volume_weight: float | None = None
    max_scale_pct: int | None = None
    scale_cooldown_hours: int | None = None
    max_daily_budget_increase: float | None = None
    broad_roas_threshold_multiplier: float | None = None
    broad_min_days_before_pause: int | None = None
    lla_scale_pct_bump: int | None = None
    lla_fatigue_spend_multiplier: float | None = None
    interest_days_decline_before_pause: int | None = None
    custom_max_scale_pct: int | None = None
