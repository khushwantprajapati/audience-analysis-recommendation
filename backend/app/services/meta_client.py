"""Meta Marketing API wrapper using facebook-business SDK."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.adsinsights import AdsInsights

from app.config import get_settings
from app.utils.crypto import decrypt_token

# Insight fields we need
INSIGHT_FIELDS = [
    AdsInsights.Field.spend,
    AdsInsights.Field.impressions,
    AdsInsights.Field.clicks,
    AdsInsights.Field.ctr,
    AdsInsights.Field.cpc,
    AdsInsights.Field.actions,
    AdsInsights.Field.action_values,
]

AD_SET_FIELDS = [
    AdSet.Field.id,
    AdSet.Field.name,
    AdSet.Field.campaign_id,
    AdSet.Field.daily_budget,
    AdSet.Field.created_time,
    AdSet.Field.targeting,
]


def _ensure_act_prefix(account_id: str) -> str:
    if not account_id.startswith("act_"):
        return f"act_{account_id}"
    return account_id


def init_api(access_token: str) -> None:
    """Initialize the Facebook Ads API with the given token."""
    settings = get_settings()
    plain = decrypt_token(access_token) if access_token else ""
    FacebookAdsApi.init(
        app_id=settings.meta_app_id or None,
        app_secret=settings.meta_app_secret or None,
        access_token=plain,
    )


def _parse_actions(insight: dict, action_type: str) -> int:
    """Sum count for action_type from insight['actions'] (list of {action_type, value})."""
    actions = insight.get("actions") or []
    total = 0
    for a in actions:
        if isinstance(a, dict) and a.get("action_type") == action_type:
            total += int(a.get("value", 0) or 0)
    return total


def _parse_action_values(insight: dict, action_type: str) -> float:
    """Sum value for action_type from insight['action_values']."""
    values = insight.get("action_values") or []
    total = 0.0
    for v in values:
        if isinstance(v, dict) and v.get("action_type") == action_type:
            total += float(v.get("value", 0) or 0)
    return total


def get_ad_sets(access_token: str, account_id: str) -> list[dict]:
    """Fetch all ad sets for the account. Returns list of dicts with id, name, campaign_id, daily_budget, created_time, targeting."""
    init_api(access_token)
    account_id = _ensure_act_prefix(account_id)
    account = AdAccount(account_id)
    ad_sets = account.get_ad_sets(fields=AD_SET_FIELDS)
    result = []
    for ad_set in ad_sets:
        d = dict(ad_set)
        result.append(d)
    return result


def get_insights_for_ad_set(
    access_token: str,
    ad_set_id: str,
    date_preset: str,
) -> list[dict]:
    """
    Get insights for one ad set over a time range.
    date_preset: 'last_1d', 'last_3d', 'last_7d', or use time_range.
    Returns list of insight dicts (one per day if breakdown by day).
    """
    init_api(access_token)
    from facebook_business.adobjects.adset import AdSet as AdSetObj
    ad_set = AdSetObj(ad_set_id)
    params = {"date_preset": date_preset, "time_increment": 1}
    insights = ad_set.get_insights(fields=INSIGHT_FIELDS, params=params)
    result = []
    for ins in insights:
        result.append(dict(ins))
    return result


def get_insights_aggregate(
    access_token: str,
    ad_set_id: str,
    date_preset: str,
) -> Optional[dict]:
    """
    Get single aggregate insight for ad set over the period (no time_increment).
    Returns one dict with spend, purchases, revenue, etc. or None if no data.
    """
    init_api(access_token)
    from facebook_business.adobjects.adset import AdSet as AdSetObj
    ad_set = AdSetObj(ad_set_id)
    params = {"date_preset": date_preset}
    insights = ad_set.get_insights(fields=INSIGHT_FIELDS, params=params)
    for ins in insights:
        d = dict(ins)
        spend = float(d.get("spend") or 0)
        purchases = _parse_actions(d, "purchase") + _parse_actions(d, "omni_purchase")
        revenue = _parse_action_values(d, "purchase") + _parse_action_values(d, "omni_purchase")
        clicks = int(d.get("clicks") or 0)
        impressions = int(d.get("impressions") or 0)
        ctr = float(d.get("ctr") or 0) if d.get("ctr") else None
        cpc = float(d.get("cpc") or 0) if d.get("cpc") else None
        roas = (revenue / spend) if spend > 0 else None
        cpa = (spend / purchases) if purchases > 0 else None
        cvr = (purchases / clicks) if clicks > 0 else None
        return {
            "spend": spend,
            "revenue": revenue,
            "purchases": purchases,
            "impressions": impressions,
            "clicks": clicks,
            "ctr": ctr,
            "cpc": cpc,
            "roas": roas,
            "cpa": cpa,
            "cvr": cvr,
            "date_start": d.get("date_start"),
            "date_stop": d.get("date_stop"),
        }
    return None


def infer_audience_type(ad_set_data: dict) -> str:
    """Infer BROAD, INTEREST, LLA, CUSTOM from targeting."""
    targeting = ad_set_data.get("targeting") or {}
    if not targeting:
        return "BROAD"
    # Check for lookalike
    if targeting.get("flexible_spec") or targeting.get("custom_audiences"):
        for spec in (targeting.get("flexible_spec") or []) + (targeting.get("custom_audiences") or []):
            if isinstance(spec, dict):
                for k, v in spec.items():
                    if "lookalike" in str(k).lower() or (isinstance(v, dict) and v.get("lookalike_spec")):
                        return "LLA"
    if targeting.get("custom_audiences"):
        return "CUSTOM"
    if targeting.get("interests") or targeting.get("flexible_spec"):
        return "INTEREST"
    return "BROAD"
