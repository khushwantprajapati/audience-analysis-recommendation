"""Pull ad set data from Meta API and store in DB."""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models import Account, Audience, MetricSnapshot
from app.services.meta_client import (
    get_ad_sets,
    _batch_insights,
    aggregate_windows_from_rows,
    infer_audience_type,
    _ensure_act_prefix,
    get_sync_lock,
)
from app.utils.crypto import decrypt_token

# Valid Meta date presets
VALID_DATE_PRESETS = {
    "yesterday", "last_3d", "last_7d", "last_14d", "last_28d", "last_30d",
    "last_90d", "this_month", "last_month", "this_quarter", "last_quarter",
    "this_year", "last_year", "maximum", "data_maximum",
}


def _parse_launched_at(ad_set_data: dict) -> datetime | None:
    ct = ad_set_data.get("created_time")
    if not ct:
        return None
    if isinstance(ct, datetime):
        return ct.replace(tzinfo=timezone.utc) if ct.tzinfo is None else ct
    from dateutil import parser
    try:
        return parser.parse(ct)
    except Exception:
        return None


def _budget_from_ad_set(ad_set_data: dict) -> Decimal | None:
    b = ad_set_data.get("daily_budget")
    if b is None:
        return None
    try:
        return Decimal(str(b)) / 100 if int(b) > 10000 else Decimal(str(b))
    except (TypeError, ValueError):
        return None


def sync_account(account_id: str, db: Session, date_preset: str = "last_7d") -> dict:
    """
    Sync ad sets and insights for an account.
    Uses batch API to fetch insights for all ad sets in chunks of 50, then
    aggregates into 1d/3d/7d windows locally.
    date_preset: controls how far back to fetch (default last_7d).
    Returns summary dict.
    """
    if date_preset not in VALID_DATE_PRESETS:
        date_preset = "last_7d"

    # Prevent concurrent syncs on the same account
    lock = get_sync_lock(account_id)
    if not lock.acquire(blocking=False):
        logger.warning(f"Sync already in progress for account {account_id}, skipping")
        return {"error": "Sync already in progress for this account. Please wait."}

    try:
        return _do_sync(account_id, db, date_preset)
    finally:
        lock.release()


def _do_sync(account_id: str, db: Session, date_preset: str) -> dict:
    """Internal sync implementation."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return {"error": "Account not found"}
    token = decrypt_token(account.access_token)
    meta_id = _ensure_act_prefix(account.meta_account_id)
    logger.info(f"Syncing account {account.account_name} ({meta_id}) with preset={date_preset}")

    summary = {"audiences_created": 0, "audiences_updated": 0, "snapshots_created": 0, "errors": []}

    # Use a single httpx.Client for the entire sync (connection reuse)
    with httpx.Client(http2=False) as client:
        # Step 1: Fetch all ad sets (1 API call + pagination)
        try:
            ad_sets_data = get_ad_sets(client, token, meta_id)
            logger.info(f"Fetched {len(ad_sets_data)} ad sets from Meta")
        except Exception as e:
            logger.error(f"Failed to fetch ad sets: {e}", exc_info=True)
            summary["errors"].append(str(e))
            return summary

        # Step 2: Upsert audiences in DB and collect ad set IDs
        ad_set_id_to_audience: dict[str, Audience] = {}
        for ad_set_data in ad_sets_data:
            meta_ad_set_id = ad_set_data.get("id")
            if not meta_ad_set_id:
                continue
            name = ad_set_data.get("name") or meta_ad_set_id
            audience_type = infer_audience_type(ad_set_data)
            launched_at = _parse_launched_at(ad_set_data)
            current_budget = _budget_from_ad_set(ad_set_data)
            campaign_id = ad_set_data.get("campaign_id")
            campaign_name = None
            if isinstance(ad_set_data.get("campaign"), dict):
                campaign_name = ad_set_data["campaign"].get("name")

            audience = db.query(Audience).filter(Audience.meta_ad_set_id == meta_ad_set_id).first()
            if not audience:
                audience = Audience(
                    id=str(uuid.uuid4()),
                    account_id=account_id,
                    meta_ad_set_id=meta_ad_set_id,
                    name=name,
                    audience_type=audience_type,
                    launched_at=launched_at,
                    current_budget=current_budget,
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                )
                db.add(audience)
                db.flush()
                summary["audiences_created"] += 1
            else:
                audience.name = name
                audience.audience_type = audience_type
                audience.launched_at = launched_at
                audience.current_budget = current_budget
                audience.campaign_id = campaign_id
                audience.campaign_name = campaign_name
                summary["audiences_updated"] += 1

            ad_set_id_to_audience[meta_ad_set_id] = audience

        # Step 3: Batch-fetch insights for ALL ad sets
        # This uses Meta's Batch API: up to 50 ad sets per call
        ad_set_ids = list(ad_set_id_to_audience.keys())
        logger.info(f"Batch-fetching insights for {len(ad_set_ids)} ad sets (preset={date_preset})")

        try:
            all_daily_rows = _batch_insights(client, token, ad_set_ids, date_preset)
        except Exception as e:
            logger.error(f"Batch insights failed: {e}", exc_info=True)
            summary["errors"].append(f"Batch insights: {e}")
            db.commit()
            return summary

        # Step 4: Aggregate and store snapshots
        today = date.today()
        for meta_ad_set_id, daily_rows in all_daily_rows.items():
            audience = ad_set_id_to_audience.get(meta_ad_set_id)
            if not audience:
                continue

            if not daily_rows:
                # No data for this ad set — not an error, just no impressions
                continue

            windows = aggregate_windows_from_rows(daily_rows)

            for window_days, ins in windows.items():
                existing = (
                    db.query(MetricSnapshot)
                    .filter(
                        MetricSnapshot.audience_id == audience.id,
                        MetricSnapshot.snapshot_date == today,
                        MetricSnapshot.window_days == window_days,
                    )
                    .first()
                )
                spend = Decimal(str(ins["spend"]))
                revenue = Decimal(str(ins["revenue"]))
                purchases = int(ins["purchases"])
                impressions = int(ins["impressions"])
                clicks = int(ins["clicks"])
                ctr = ins.get("ctr")
                cpc = Decimal(str(ins["cpc"])) if ins.get("cpc") is not None else None
                roas = Decimal(str(ins["roas"])) if ins.get("roas") is not None else None
                cpa = Decimal(str(ins["cpa"])) if ins.get("cpa") is not None else None
                cvr = ins.get("cvr")

                if existing:
                    existing.spend = spend
                    existing.revenue = revenue
                    existing.purchases = purchases
                    existing.impressions = impressions
                    existing.clicks = clicks
                    existing.ctr = ctr
                    existing.cpc = cpc
                    existing.roas = roas
                    existing.cpa = cpa
                    existing.cvr = cvr
                else:
                    snap = MetricSnapshot(
                        id=str(uuid.uuid4()),
                        audience_id=audience.id,
                        snapshot_date=today,
                        window_days=window_days,
                        spend=spend,
                        revenue=revenue,
                        purchases=purchases,
                        impressions=impressions,
                        clicks=clicks,
                        ctr=ctr,
                        cpc=cpc,
                        roas=roas,
                        cpa=cpa,
                        cvr=cvr,
                    )
                    db.add(snap)
                    summary["snapshots_created"] += 1

        db.commit()

    logger.info(
        f"Sync complete: {summary['audiences_created']} created, "
        f"{summary['audiences_updated']} updated, "
        f"{summary['snapshots_created']} snapshots, "
        f"{len(summary['errors'])} errors"
    )
    if summary["errors"]:
        for err in summary["errors"][:5]:
            logger.warning(f"  Sync error: {err}")
    return summary
