"""Meta Marketing API wrapper using direct Graph API calls (no SDK overhead)."""
import logging
import time
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.utils.crypto import decrypt_token

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v18.0"

# Fields we request
AD_SET_FIELDS = "id,name,campaign_id,daily_budget,created_time,targeting"
INSIGHT_FIELDS = "spend,impressions,clicks,ctr,cpc,actions,action_values"


def _ensure_act_prefix(account_id: str) -> str:
    if not account_id.startswith("act_"):
        return f"act_{account_id}"
    return account_id


def _graph_get(access_token: str, path: str, params: dict | None = None, retries: int = 2) -> dict:
    """Make a GET request to the Graph API with retry on rate limit."""
    params = params or {}
    params["access_token"] = access_token
    url = f"{GRAPH_BASE}/{path}" if not path.startswith("http") else path

    for attempt in range(retries + 1):
        resp = httpx.get(url, params=params, timeout=30)
        data = resp.json()

        if resp.status_code == 200:
            return data

        error = data.get("error", {})
        code = error.get("code")
        if code in (17, 32, 4) and attempt < retries:
            wait = 30 * (attempt + 1)
            logger.warning(f"Rate limited (code {code}), waiting {wait}s before retry {attempt + 1}/{retries}")
            time.sleep(wait)
            continue

        raise Exception(
            f"Graph API error: {error.get('message', resp.text)} "
            f"(code={code}, status={resp.status_code})"
        )
    return {}


def _parse_actions(insight: dict, action_type: str) -> int:
    actions = insight.get("actions") or []
    total = 0
    for a in actions:
        if isinstance(a, dict) and a.get("action_type") == action_type:
            total += int(a.get("value", 0) or 0)
    return total


def _parse_action_values(insight: dict, action_type: str) -> float:
    values = insight.get("action_values") or []
    total = 0.0
    for v in values:
        if isinstance(v, dict) and v.get("action_type") == action_type:
            total += float(v.get("value", 0) or 0)
    return total


def _compute_metrics_from_row(d: dict) -> dict:
    """Parse a single insight row into our standard metrics dict."""
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
    }


def _aggregate_daily_rows(rows: list[dict]) -> dict:
    """Sum daily insight rows into one aggregate."""
    spend = sum(float(r.get("spend") or 0) for r in rows)
    clicks = sum(int(r.get("clicks") or 0) for r in rows)
    impressions = sum(int(r.get("impressions") or 0) for r in rows)
    purchases = sum(_parse_actions(r, "purchase") + _parse_actions(r, "omni_purchase") for r in rows)
    revenue = sum(_parse_action_values(r, "purchase") + _parse_action_values(r, "omni_purchase") for r in rows)
    ctr = (clicks / impressions * 100) if impressions > 0 else None
    cpc = (spend / clicks) if clicks > 0 else None
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
    }


def get_ad_sets(access_token: str, account_id: str) -> list[dict]:
    """Fetch all ad sets for the account via Graph API."""
    account_id = _ensure_act_prefix(account_id)
    logger.info(f"Fetching ad sets for {account_id}")
    data = _graph_get(access_token, f"{account_id}/adsets", {
        "fields": AD_SET_FIELDS,
        "limit": 200,
    })
    ad_sets = data.get("data", [])
    logger.info(f"Got {len(ad_sets)} ad sets")
    while data.get("paging", {}).get("next"):
        data = _graph_get(access_token, data["paging"]["next"])
        ad_sets.extend(data.get("data", []))
    return ad_sets


def get_insights_daily(
    access_token: str,
    ad_set_id: str,
    date_preset: str,
) -> list[dict]:
    """
    Get daily breakdown insights for an ad set. One API call.
    Returns list of raw daily rows sorted by date_start.
    """
    data = _graph_get(access_token, f"{ad_set_id}/insights", {
        "fields": INSIGHT_FIELDS,
        "date_preset": date_preset,
        "time_increment": 1,
    })
    rows = data.get("data", [])
    rows.sort(key=lambda r: r.get("date_start", ""))
    return rows


def get_insights_windows(
    access_token: str,
    ad_set_id: str,
    date_preset: str = "last_7d",
) -> dict[int, dict]:
    """
    Single API call: fetch daily breakdown, then aggregate into 1d, 3d, 7d windows.
    Returns {1: {...}, 3: {...}, 7: {...}} with metrics for each window.
    Empty dict if no data.
    """
    rows = get_insights_daily(access_token, ad_set_id, date_preset)
    if not rows:
        return {}
    result = {}
    # Full range = all rows (whatever the preset covers)
    n = len(rows)
    # 1d = last row only
    if n >= 1:
        result[1] = _compute_metrics_from_row(rows[-1])
    # 3d = last 3 rows aggregated
    if n >= 3:
        result[3] = _aggregate_daily_rows(rows[-3:])
    elif n >= 1:
        result[3] = _aggregate_daily_rows(rows)
    # 7d = all rows aggregated (since preset is last_7d)
    result[7] = _aggregate_daily_rows(rows)
    return result


def get_insights_windows_flexible(
    access_token: str,
    ad_set_id: str,
    date_preset: str = "last_7d",
) -> dict[int, dict]:
    """
    Single API call with any date_preset. Fetches daily breakdown and aggregates
    into 1d, 3d, 7d windows (using the last N days from available data).
    Also stores the full-range aggregate under the total day count.
    """
    rows = get_insights_daily(access_token, ad_set_id, date_preset)
    if not rows:
        return {}
    result = {}
    n = len(rows)
    # Always compute 1d, 3d, 7d from the tail
    if n >= 1:
        result[1] = _compute_metrics_from_row(rows[-1])
    if n >= 3:
        result[3] = _aggregate_daily_rows(rows[-3:])
    elif n >= 1:
        result[3] = _aggregate_daily_rows(rows)
    if n >= 7:
        result[7] = _aggregate_daily_rows(rows[-7:])
    elif n >= 1:
        result[7] = _aggregate_daily_rows(rows)
    return result


def infer_audience_type(ad_set_data: dict) -> str:
    """Infer BROAD, INTEREST, LLA, CUSTOM from targeting."""
    targeting = ad_set_data.get("targeting") or {}
    if not targeting:
        return "BROAD"
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
