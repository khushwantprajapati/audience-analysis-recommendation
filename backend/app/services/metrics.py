"""Metrics normalization and composite scoring."""
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Audience, MetricSnapshot


def _get_latest_snapshot(db: Session, audience_id: str, window_days: int = 7) -> Optional[MetricSnapshot]:
    today = date.today()
    return (
        db.query(MetricSnapshot)
        .filter(
            MetricSnapshot.audience_id == audience_id,
            MetricSnapshot.window_days == window_days,
            MetricSnapshot.snapshot_date <= today,
        )
        .order_by(MetricSnapshot.snapshot_date.desc())
        .first()
    )


def get_account_benchmarks(db: Session, account_id: str) -> dict:
    """
    Compute account-level benchmarks from audiences with 7d snapshots above MIN_SPEND.
    Returns: account_avg_roas, median_spend, account_avg_cvr, target_cpa (from config).
    """
    settings = get_settings()
    min_spend = float(settings.min_spend)
    audiences = db.query(Audience).filter(Audience.account_id == account_id).all()
    roas_list = []
    spend_list = []
    cvr_list = []
    for a in audiences:
        snap = _get_latest_snapshot(db, a.id, 7)
        if not snap or float(snap.spend or 0) < min_spend:
            continue
        if snap.roas is not None and float(snap.roas) > 0:
            roas_list.append(float(snap.roas))
        spend_list.append(float(snap.spend or 0))
        if snap.cvr is not None and float(snap.cvr) > 0:
            cvr_list.append(float(snap.cvr))
    account_avg_roas = sum(roas_list) / len(roas_list) if roas_list else 1.0
    median_spend = median(spend_list) if spend_list else min_spend
    account_avg_cvr = sum(cvr_list) / len(cvr_list) if cvr_list else 0.01
    return {
        "account_avg_roas": account_avg_roas,
        "median_spend": median_spend,
        "account_avg_cvr": account_avg_cvr,
        "target_cpa": float(settings.max_daily_budget_increase),  # placeholder; could be per-account
    }


def _float_or_none(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_audience_metrics(
    db: Session,
    audience_id: str,
    account_benchmarks: Optional[dict] = None,
    account_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Compute normalized metrics and composite score for one audience.
    Uses 7d snapshot. If account_benchmarks not provided, fetches using account_id.
    Returns dict with raw + normalized + composite_score, or None if no snapshot.
    """
    snap = _get_latest_snapshot(db, audience_id, 7)
    if not snap:
        return None
    if not account_id:
        aud = db.query(Audience).filter(Audience.id == audience_id).first()
        account_id = aud.account_id if aud else None
    if account_id and not account_benchmarks:
        account_benchmarks = get_account_benchmarks(db, account_id)
    elif not account_benchmarks and account_id:
        account_benchmarks = get_account_benchmarks(db, account_id)
    if not account_benchmarks:
        account_benchmarks = {"account_avg_roas": 1.0, "median_spend": get_settings().min_spend, "account_avg_cvr": 0.01}

    account_avg_roas = account_benchmarks["account_avg_roas"]
    median_spend = account_benchmarks["median_spend"]
    account_avg_cvr = account_benchmarks["account_avg_cvr"]

    roas = _float_or_none(snap.roas)
    spend = _float_or_none(snap.spend) or 0
    cvr = _float_or_none(snap.cvr) or 0
    purchases = int(snap.purchases or 0)

    normalized_roas = (roas / account_avg_roas) if (roas and account_avg_roas) else 0
    normalized_spend = (spend / median_spend) if median_spend else 0
    normalized_cvr = (cvr / account_avg_cvr) if (cvr and account_avg_cvr) else 0
    # Purchase volume score: cap at 2x median purchase count for 7d
    acc_id = account_id or (db.query(Audience).filter(Audience.id == audience_id).first().account_id if db.query(Audience).filter(Audience.id == audience_id).first() else None)
    all_purchases = []
    if acc_id:
        snaps = db.query(MetricSnapshot).join(Audience).filter(
            Audience.account_id == acc_id,
            MetricSnapshot.window_days == 7,
        ).all()
        all_purchases = [int(s.purchases or 0) for s in snaps]
    median_purchases = median(all_purchases) if all_purchases else 1
    purchase_volume_score = min(2.0, (purchases / median_purchases) if median_purchases else 0)

    settings = get_settings()
    composite = (
        normalized_roas * settings.roas_weight
        + normalized_spend * settings.spend_weight
        + normalized_cvr * settings.cvr_weight
        + purchase_volume_score * settings.volume_weight
    )

    return {
        "audience_id": audience_id,
        "snapshot_id": snap.id,
        "snapshot_date": snap.snapshot_date,
        "window_days": 7,
        "spend": spend,
        "revenue": _float_or_none(snap.revenue),
        "purchases": purchases,
        "roas": roas,
        "cpa": _float_or_none(snap.cpa),
        "cvr": cvr,
        "clicks": int(snap.clicks or 0),
        "impressions": int(snap.impressions or 0),
        "normalized_roas": normalized_roas,
        "normalized_spend": normalized_spend,
        "normalized_cvr": normalized_cvr,
        "purchase_volume_score": purchase_volume_score,
        "composite_score": round(composite, 4),
        "account_avg_roas": account_avg_roas,
        "median_spend": median_spend,
    }


def get_time_based_metrics(db: Session, audience_id: str) -> dict:
    """
    Compute ROAS slope, CPA volatility, spend acceleration from daily snapshots (window_days=1).
    """
    today = date.today()
    snapshots = (
        db.query(MetricSnapshot)
        .filter(
            MetricSnapshot.audience_id == audience_id,
            MetricSnapshot.window_days == 1,
            MetricSnapshot.snapshot_date <= today,
            MetricSnapshot.snapshot_date >= today - timedelta(days=14),
        )
        .order_by(MetricSnapshot.snapshot_date.asc())
        .all()
    )
    if len(snapshots) < 2:
        return {"roas_slope": 0, "cpa_volatility": 0, "spend_acceleration": 1.0, "dod_roas_change": 0}

    roas_series = [_float_or_none(s.roas) or 0 for s in snapshots]
    cpa_series = [_float_or_none(s.cpa) or 0 for s in snapshots if _float_or_none(s.cpa)]
    spend_series = [_float_or_none(s.spend) or 0 for s in snapshots]

    # Linear regression slope for ROAS
    n = len(roas_series)
    x_mean = (n - 1) / 2
    y_mean = sum(roas_series) / n
    num = sum((i - x_mean) * (roas_series[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    roas_slope = (num / den) if den else 0

    # CPA std dev
    import statistics
    cpa_volatility = statistics.stdev(cpa_series) / (statistics.mean(cpa_series) or 1) if len(cpa_series) >= 2 else 0

    # Spend acceleration: (spend_3d/3) / (spend_7d/7)
    last_7 = spend_series[-7:] if len(spend_series) >= 7 else spend_series
    last_3 = spend_series[-3:] if len(spend_series) >= 3 else spend_series
    spend_7d = sum(last_7)
    spend_3d = sum(last_3)
    daily_7 = spend_7d / 7 if len(last_7) == 7 else (spend_7d / len(last_7)) if last_7 else 1
    daily_3 = spend_3d / 3 if len(last_3) == 3 else (spend_3d / len(last_3)) if last_3 else 1
    spend_acceleration = (daily_3 / daily_7) if daily_7 else 1.0

    dod_roas_change = 0
    if len(roas_series) >= 2 and roas_series[-2]:
        dod_roas_change = (roas_series[-1] - roas_series[-2]) / roas_series[-2]

    return {
        "roas_slope": round(roas_slope, 6),
        "cpa_volatility": round(cpa_volatility, 4),
        "spend_acceleration": round(spend_acceleration, 4),
        "dod_roas_change": round(dod_roas_change, 4),
    }
