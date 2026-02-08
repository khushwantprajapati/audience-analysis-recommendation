"""Deterministic rule engine: performance buckets, trend states, decision matrix, guardrails."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Audience, MetricSnapshot, Recommendation
from app.services.metrics import (
    get_account_benchmarks,
    compute_audience_metrics,
    get_time_based_metrics,
)


# --- Performance buckets ---
def classify_performance(normalized_roas: float, audience_type: str = "") -> str:
    settings = get_settings()
    threshold_winner = settings.winner_threshold
    threshold_loser = settings.loser_threshold
    if audience_type == "BROAD":
        threshold_winner *= settings.broad_roas_threshold_multiplier
        threshold_loser *= settings.broad_roas_threshold_multiplier
    if normalized_roas >= threshold_winner:
        return "WINNER"
    if normalized_roas >= threshold_loser:
        return "AVERAGE"
    return "LOSER"


# --- Trend states ---
def classify_trend(
    roas_slope: float,
    cpa_volatility: float,
    spend_acceleration: float,
) -> str:
    settings = get_settings()
    if cpa_volatility > settings.volatile_cpa_std:
        return "VOLATILE"
    if roas_slope > settings.improving_slope:
        return "IMPROVING"
    if roas_slope < settings.declining_slope:
        return "DECLINING"
    return "STABLE"


# --- Decision matrix ---
DECISION_MATRIX = {
    ("WINNER", "STABLE"): "SCALE",
    ("WINNER", "IMPROVING"): "SCALE",
    ("WINNER", "DECLINING"): "HOLD",
    ("WINNER", "VOLATILE"): "HOLD",
    ("AVERAGE", "STABLE"): "HOLD",
    ("AVERAGE", "IMPROVING"): "HOLD",
    ("AVERAGE", "DECLINING"): "PAUSE",
    ("AVERAGE", "VOLATILE"): "HOLD",
    ("LOSER", "STABLE"): "PAUSE",
    ("LOSER", "IMPROVING"): "HOLD",
    ("LOSER", "DECLINING"): "PAUSE",
    ("LOSER", "VOLATILE"): "PAUSE",
}


def get_scale_percentage(audience_type: str) -> int:
    settings = get_settings()
    base = settings.max_scale_pct
    if audience_type == "LLA":
        base = min(30, base + settings.lla_scale_pct_bump)
    if audience_type == "CUSTOM":
        base = min(base, settings.custom_max_scale_pct)
    return base


def apply_guardrails(
    action: str,
    audience: Audience,
    db: Session,
    metrics: dict,
) -> tuple[str, Optional[int]]:
    """
    Apply guardrails. Returns (final_action, scale_percentage or None).
    - No PAUSE if spend < MIN_SPEND
    - SCALE capped and cooldown checked (simplified: no scale history table yet)
    """
    settings = get_settings()
    spend = metrics.get("spend") or 0
    min_spend = float(settings.min_spend)

    if action == "PAUSE" and spend < min_spend:
        return "HOLD", None
    if action == "SCALE":
        scale_pct = get_scale_percentage(audience.audience_type)
        # Cooldown: would need last_scale_at; skip for now or check last recommendation
        last_scale = (
            db.query(Recommendation)
            .filter(
                Recommendation.audience_id == audience.id,
                Recommendation.action == "SCALE",
            )
            .order_by(Recommendation.generated_at.desc())
            .first()
        )
        if last_scale and last_scale.generated_at:
            from datetime import datetime, timezone
            then = last_scale.generated_at
            if then.tzinfo is None:
                then = then.replace(tzinfo=timezone.utc)
            delta = (datetime.now(timezone.utc) - then).total_seconds()
            if delta < settings.scale_cooldown_hours * 3600:
                return "HOLD", None
        return "SCALE", scale_pct
    return action, None


def run_rules_for_audience(
    db: Session,
    audience_id: str,
    account_id: str,
) -> Optional[dict]:
    """
    Run rule engine for one audience. Returns dict with action, bucket, trend_state,
    scale_percentage, composite_score, metrics, or None if filtered by noise.
    """
    settings = get_settings()
    audience = db.query(Audience).filter(Audience.id == audience_id).first()
    if not audience:
        return None
    metrics = compute_audience_metrics(db, audience_id, account_id=account_id)
    if not metrics:
        return None
    spend = metrics.get("spend") or 0
    purchases = metrics.get("purchases") or 0
    # Noise filter
    if spend < settings.min_spend or purchases < settings.min_purchases:
        return None
    if audience.launched_at:
        from datetime import datetime, timezone
        age_days = (datetime.now(timezone.utc) - audience.launched_at.replace(tzinfo=timezone.utc)).days
        if age_days < settings.min_age_days:
            return None

    time_metrics = get_time_based_metrics(db, audience_id)
    bucket = classify_performance(
        metrics.get("normalized_roas") or 0,
        audience.audience_type,
    )
    trend_state = classify_trend(
        time_metrics.get("roas_slope") or 0,
        time_metrics.get("cpa_volatility") or 0,
        time_metrics.get("spend_acceleration") or 1,
    )
    action = DECISION_MATRIX.get((bucket, trend_state), "HOLD")
    action, scale_pct = apply_guardrails(action, audience, db, metrics)

    return {
        "audience_id": audience_id,
        "audience_name": audience.name,
        "audience_type": audience.audience_type,
        "action": action,
        "scale_percentage": scale_pct,
        "performance_bucket": bucket,
        "trend_state": trend_state,
        "composite_score": metrics.get("composite_score"),
        "metrics": metrics,
        "time_metrics": time_metrics,
        "account_avg_roas": metrics.get("account_avg_roas"),
    }


def run_rules_for_account(db: Session, account_id: str) -> list[dict]:
    """Run rule engine for all eligible audiences in the account."""
    audiences = db.query(Audience).filter(Audience.account_id == account_id).all()
    results = []
    for a in audiences:
        r = run_rules_for_audience(db, a.id, account_id)
        if r:
            results.append(r)
    return results
