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
settings = get_settings()

GRAPH_BASE = "https://graph.facebook.com/v18.0"

# Fields we request
AD_SET_FIELDS = "id,name,campaign_id,daily_budget,created_time,targeting"
INSIGHT_FIELDS = "spend,impressions,clicks,ctr,cpc,actions,action_values"

# ── Adaptive rate-limit state ────────────────────────────────────
_rate_lock = threading.Lock()
_usage_pct: float = 0.0          # last known API usage percentage (0-100)
_last_call_ts: float = 0.0       # timestamp of last API call
_rate_limited_until: float = 0.0  # don't make any calls before this time
_consecutive_rate_limits: int = 0  # track consecutive rate limits for global backoff

# Delay thresholds based on usage %
_DELAY_MAP = [
    (80, 15.0),   # >=80% usage → 15s between calls
    (60, 8.0),    # >=60% → 8s
    (40, 4.0),    # >=40% → 4s
    (20, 2.0),    # >=20% → 2s
    (0, max(settings.meta_base_delay_seconds, 0.5)),
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
    return 0.5


def _mark_rate_limited(backoff_seconds: float) -> None:
    """Mark that we've been rate limited — all subsequent calls must wait."""
    global _usage_pct, _rate_limited_until, _consecutive_rate_limits
    with _rate_lock:
        _usage_pct = 100.0  # Force max delay for future calls
        _rate_limited_until = time.time() + min(backoff_seconds, settings.meta_max_backoff_seconds)
        _consecutive_rate_limits += 1
    logger.info(
        f"Rate limit flagged: no API calls for {backoff_seconds:.0f}s "
        f"(consecutive: {_consecutive_rate_limits})"
    )


def _clear_rate_limit() -> None:
    """Clear rate limit flag after a successful call."""
    global _consecutive_rate_limits
    with _rate_lock:
        _consecutive_rate_limits = 0


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
                _usage_pct = max(max_pct, _usage_pct * 0.8)  # decay slowly
            if max_pct >= 40:
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
                _usage_pct = max(max_pct, _usage_pct * 0.8)
            if max_pct >= 40:
                logger.info(f"Meta API usage (app): {max_pct:.0f}%")
        except (json.JSONDecodeError, TypeError):
            pass


def _adaptive_wait() -> None:
    """Wait the appropriate amount based on current rate limit state."""
    global _last_call_ts

    # First: respect any hard rate-limit cooldown
    with _rate_lock:
        now = time.time()
        if _rate_limited_until > now:
            wait_for = _rate_limited_until - now
            logger.info(f"Global rate-limit cooldown: waiting {wait_for:.0f}s")
            time.sleep(wait_for)

    # Then: apply adaptive delay between calls
    delay = _get_adaptive_delay()
    with _rate_lock:
        elapsed = time.time() - _last_call_ts
        if elapsed < delay:
            time.sleep(delay - elapsed)
        _last_call_ts = time.time()


def _ensure_act_prefix(account_id: str) -> str:
    if not account_id.startswith("act_"):
        return f"act_{account_id}"
    return account_id


def _get_retry_wait_seconds(headers: httpx.Headers, attempt: int) -> int:
    """Use Retry-After header when present, otherwise exponential backoff."""
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            return min(int(float(retry_after)), settings.meta_max_backoff_seconds)
        except (TypeError, ValueError):
            pass
    return min(60 * (2 ** attempt), settings.meta_max_backoff_seconds)


def _graph_get(
    client: httpx.Client,
    access_token: str,
    path: str,
    params: dict | None = None,
    retries: int = 3,
) -> dict:
    """Make a GET request to the Graph API with global backoff on rate limit."""
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
            _clear_rate_limit()
            return data

        error = data.get("error", {})
        code = error.get("code")

        if code in (17, 32, 4) and attempt < retries:
            # Exponential backoff: 60s, 120s, 240s — and block ALL calls globally
            wait = _get_retry_wait_seconds(resp.headers, attempt)
            _mark_rate_limited(wait)
            logger.warning(
                f"Rate limited (code {code}), "
                f"global backoff {wait}s — retry {attempt + 1}/{retries}"
            )
            time.sleep(wait)
            continue

        raise Exception(
            f"Graph API error: {error.get('message', resp.text)} "
            f"(code={code}, status={resp.status_code})"
        )
    # All retries exhausted without success or explicit error
    raise Exception("Graph API call failed after all retries")


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

BATCH_SIZE = max(1, min(settings.meta_batch_size, 50))  # Meta allows max 50 per batch


BATCH_RETRIES = 3


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
    On rate limit, retries the same batch with exponential backoff (never falls back
    to individual calls, which would make the rate limit worse).
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

        chunk_result = _send_batch_with_retry(client, access_token, chunk, batch_requests, date_preset)
        result.update(chunk_result)

    return result


def _send_batch_with_retry(
    client: httpx.Client,
    access_token: str,
    chunk: list[str],
    batch_requests: list[dict],
    date_preset: str = "last_7d",
) -> dict[str, list[dict]]:
    """Send a batch request with retries on rate limit. Returns {ad_set_id: [rows]}."""
    result: dict[str, list[dict]] = {}

    for attempt in range(BATCH_RETRIES + 1):
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
            error_data = {}
            try:
                error_data = resp.json()
            except Exception:
                pass
            error = error_data.get("error", {})
            code = error.get("code")

            if code in (17, 32, 4) and attempt < BATCH_RETRIES:
                # Exponential backoff: 60s, 120s, 240s — and block all calls globally
                wait = _get_retry_wait_seconds(resp.headers, attempt)
                _mark_rate_limited(wait)
                logger.warning(
                    f"Batch rate limited (code {code}), "
                    f"global backoff {wait}s — retry {attempt + 1}/{BATCH_RETRIES}"
                )
                time.sleep(wait)
                continue

            # Out of retries — mark all ad sets in chunk as empty
            logger.error(f"Batch failed after {BATCH_RETRIES} retries: {error.get('message', resp.text)}")
            for ad_set_id in chunk:
                result[ad_set_id] = []
            return result

        _clear_rate_limit()

        # Parse batch responses
        batch_responses = resp.json()
        if not isinstance(batch_responses, list):
            logger.error(f"Unexpected batch response type: {type(batch_responses)}")
            for ad_set_id in chunk:
                result[ad_set_id] = []
            return result

        # Check if any individual items in the batch were rate-limited
        rate_limited_ids = []
        rate_limited_errors: list[dict[str, Any]] = []
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
                err_code = error.get("code")
                if err_code in (17, 32, 4):
                    rate_limited_ids.append(ad_set_id)
                    rate_limited_errors.append(error)
                else:
                    logger.warning(
                        f"Batch item {ad_set_id} failed: "
                        f"{error.get('message', f'status {status}')}"
                    )
                    result[ad_set_id] = []

        if rate_limited_ids and attempt < BATCH_RETRIES:
            # Some items rate-limited — wait and retry just those
            wait = _get_retry_wait_seconds(resp.headers, attempt)
            _mark_rate_limited(wait)
            logger.warning(
                f"{len(rate_limited_ids)} batch items rate-limited, "
                f"global backoff {wait}s — retry {attempt + 1}/{BATCH_RETRIES}"
            )
            time.sleep(wait)
            # Rebuild batch for only the failed items
            chunk = rate_limited_ids
            batch_requests = []
            for ad_set_id in chunk:
                relative_url = (
                    f"{ad_set_id}/insights?"
                    f"fields={INSIGHT_FIELDS}&"
                    f"date_preset={date_preset}&"
                    f"time_increment=1"
                )
                batch_requests.append({"method": "GET", "relative_url": relative_url})
            continue
        elif rate_limited_ids:
            # Out of retries, mark remaining as empty
            for ad_set_id in rate_limited_ids:
                result[ad_set_id] = []

        # All done for this chunk
        return result

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
