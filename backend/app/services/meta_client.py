"""Meta Marketing API wrapper using direct Graph API calls with connection reuse,
adaptive rate limiting, and batch support."""
import json
import logging
import time
import threading
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.utils.crypto import decrypt_token

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v18.0"

# Fields we request
AD_SET_FIELDS = "id,name,campaign_id,daily_budget,created_time,targeting"
INSIGHT_FIELDS = "spend,impressions,clicks,ctr,cpc,actions,action_values"

# ── Adaptive rate-limit state ────────────────────────────────────
_rate_lock = threading.Lock()
_usage_pct: float = 0.0          # last known API usage percentage (0-100)
_last_call_ts: float = 0.0       # timestamp of last API call

# Delay thresholds based on usage %
_DELAY_MAP = [
    (80, 10.0),   # >=80% usage → 10s between calls
    (60, 5.0),    # >=60% → 5s
    (40, 2.0),    # >=40% → 2s
    (20, 1.0),    # >=20% → 1s
    (0, 0.3),     # <20%  → 0.3s
]

# ── Sync lock per account ────────────────────────────────────────
_sync_locks: dict[str, threading.Lock] = {}
_sync_locks_lock = threading.Lock()


def get_sync_lock(account_id: str) -> threading.Lock:
    """Get or create a per-account sync lock to prevent concurrent syncs."""
    with _sync_locks_lock:
        if account_id not in _sync_locks:
            _sync_locks[account_id] = threading.Lock()
        return _sync_locks[account_id]


def _get_adaptive_delay() -> float:
    """Return the appropriate delay based on current API usage percentage."""
    with _rate_lock:
        for threshold, delay in _DELAY_MAP:
            if _usage_pct >= threshold:
                return delay
    return 0.3


def _update_usage_from_headers(headers: httpx.Headers) -> None:
    """Parse Meta's x-business-use-case-usage or x-app-usage headers to track API usage %."""
    global _usage_pct

    # x-business-use-case-usage: {"<ad_account_id>":[{"call_count":X,"total_cputime":Y,...}]}
    biz_usage = headers.get("x-business-use-case-usage")
    if biz_usage:
        try:
            data = json.loads(biz_usage)
            max_pct = 0.0
            for account_id, entries in data.items():
                for entry in entries:
                    for key in ("call_count", "total_cputime", "total_time"):
                        val = entry.get(key, 0)
                        if val > max_pct:
                            max_pct = val
            with _rate_lock:
                _usage_pct = max_pct
            if max_pct >= 50:
                logger.info(f"Meta API usage: {max_pct:.0f}% (delay: {_get_adaptive_delay():.1f}s)")
            return
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback: x-app-usage: {"call_count":X,"total_cputime":Y,"total_time":Z}
    app_usage = headers.get("x-app-usage")
    if app_usage:
        try:
            data = json.loads(app_usage)
            max_pct = max(
                data.get("call_count", 0),
                data.get("total_cputime", 0),
                data.get("total_time", 0),
            )
            with _rate_lock:
                _usage_pct = max_pct
            if max_pct >= 50:
                logger.info(f"Meta API usage (app): {max_pct:.0f}%")
        except (json.JSONDecodeError, TypeError):
            pass


def _adaptive_wait() -> None:
    """Wait the appropriate amount based on current rate limit usage."""
    global _last_call_ts
    delay = _get_adaptive_delay()
    with _rate_lock:
        elapsed = time.time() - _last_call_ts
        if elapsed < delay:
            sleep_for = delay - elapsed
            time.sleep(sleep_for)
        _last_call_ts = time.time()


def _ensure_act_prefix(account_id: str) -> str:
    if not account_id.startswith("act_"):
        return f"act_{account_id}"
    return account_id


def _graph_get(
    client: httpx.Client,
    access_token: str,
    path: str,
    params: dict | None = None,
    retries: int = 3,
) -> dict:
    """Make a GET request to the Graph API with adaptive delays and retry on rate limit."""
    params = params or {}
    params["access_token"] = access_token
    url = f"{GRAPH_BASE}/{path}" if not path.startswith("http") else path

    for attempt in range(retries + 1):
        _adaptive_wait()
        resp = client.get(url, params=params, timeout=30)

        # Always update usage tracking from response headers
        _update_usage_from_headers(resp.headers)

        data = resp.json()

        if resp.status_code == 200:
            return data

        error = data.get("error", {})
        code = error.get("code")

        if code in (17, 32, 4) and attempt < retries:
            # Exponential backoff: 30s, 60s, 120s
            wait = 30 * (2 ** attempt)
            logger.warning(
                f"Rate limited (code {code}, usage ~{_usage_pct:.0f}%), "
                f"waiting {wait}s before retry {attempt + 1}/{retries}"
            )
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


def get_ad_sets(client: httpx.Client, access_token: str, account_id: str) -> list[dict]:
    """Fetch all ad sets for the account via Graph API."""
    account_id = _ensure_act_prefix(account_id)
    logger.info(f"Fetching ad sets for {account_id}")
    data = _graph_get(client, access_token, f"{account_id}/adsets", {
        "fields": AD_SET_FIELDS,
        "limit": 200,
    })
    ad_sets = data.get("data", [])
    logger.info(f"Got {len(ad_sets)} ad sets")
    while data.get("paging", {}).get("next"):
        data = _graph_get(client, access_token, data["paging"]["next"])
        ad_sets.extend(data.get("data", []))
    return ad_sets


# ── Batch API ────────────────────────────────────────────────────

BATCH_SIZE = 50  # Meta allows max 50 per batch


def _batch_insights(
    client: httpx.Client,
    access_token: str,
    ad_set_ids: list[str],
    date_preset: str,
) -> dict[str, list[dict]]:
    """
    Fetch daily insight breakdowns for multiple ad sets in a single batch API call.
    Returns {ad_set_id: [daily_rows]} for each ad set.
    Meta Batch API: POST / with batch=[{method,relative_url},...] (max 50 per call).
    """
    result: dict[str, list[dict]] = {}

    for i in range(0, len(ad_set_ids), BATCH_SIZE):
        chunk = ad_set_ids[i : i + BATCH_SIZE]
        batch_requests = []
        for ad_set_id in chunk:
            relative_url = (
                f"{ad_set_id}/insights?"
                f"fields={INSIGHT_FIELDS}&"
                f"date_preset={date_preset}&"
                f"time_increment=1"
            )
            batch_requests.append({"method": "GET", "relative_url": relative_url})

        _adaptive_wait()
        resp = client.post(
            GRAPH_BASE,
            data={
                "access_token": access_token,
                "batch": json.dumps(batch_requests),
            },
            timeout=60,
        )

        _update_usage_from_headers(resp.headers)

        if resp.status_code != 200:
            error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error = error_data.get("error", {})
            code = error.get("code")
            if code in (17, 32, 4):
                # Rate limited on batch call — wait and retry this chunk
                wait = 60
                logger.warning(f"Batch rate limited (code {code}), waiting {wait}s")
                time.sleep(wait)
                # Retry this chunk individually
                for ad_set_id in chunk:
                    try:
                        rows = get_insights_daily(client, access_token, ad_set_id, date_preset)
                        result[ad_set_id] = rows
                    except Exception as e:
                        logger.warning(f"Fallback insight fetch failed for {ad_set_id}: {e}")
                        result[ad_set_id] = []
                continue
            raise Exception(f"Batch API error: {error.get('message', resp.text)} (code={code})")

        batch_responses = resp.json()
        if not isinstance(batch_responses, list):
            logger.error(f"Unexpected batch response type: {type(batch_responses)}")
            continue

        for j, batch_resp in enumerate(batch_responses):
            ad_set_id = chunk[j]
            status = batch_resp.get("code", 0)
            body_str = batch_resp.get("body", "{}")
            try:
                body = json.loads(body_str) if isinstance(body_str, str) else body_str
            except json.JSONDecodeError:
                body = {}

            if status == 200:
                rows = body.get("data", [])
                rows.sort(key=lambda r: r.get("date_start", ""))
                result[ad_set_id] = rows
            else:
                error = body.get("error", {})
                logger.warning(
                    f"Batch item {ad_set_id} failed: {error.get('message', f'status {status}')}"
                )
                result[ad_set_id] = []

    return result


def get_insights_daily(
    client: httpx.Client,
    access_token: str,
    ad_set_id: str,
    date_preset: str,
) -> list[dict]:
    """
    Get daily breakdown insights for an ad set. One API call.
    Returns list of raw daily rows sorted by date_start.
    """
    data = _graph_get(client, access_token, f"{ad_set_id}/insights", {
        "fields": INSIGHT_FIELDS,
        "date_preset": date_preset,
        "time_increment": 1,
    })
    rows = data.get("data", [])
    rows.sort(key=lambda r: r.get("date_start", ""))
    return rows


def aggregate_windows_from_rows(rows: list[dict]) -> dict[int, dict]:
    """
    Aggregate daily rows into 1d, 3d, 7d windows.
    Returns {1: {...}, 3: {...}, 7: {...}} with metrics for each window.
    """
    if not rows:
        return {}
    result = {}
    n = len(rows)
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


def get_insights_windows_flexible(
    client: httpx.Client,
    access_token: str,
    ad_set_id: str,
    date_preset: str = "last_7d",
) -> dict[int, dict]:
    """
    Single API call with any date_preset. Fetches daily breakdown and aggregates
    into 1d, 3d, 7d windows (using the last N days from available data).
    """
    rows = get_insights_daily(client, access_token, ad_set_id, date_preset)
    return aggregate_windows_from_rows(rows)


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
