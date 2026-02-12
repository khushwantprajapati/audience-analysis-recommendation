"""Pull ad set data from Meta API and store in DB."""
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Account, Audience, MetricSnapshot
from app.services.meta_client import (
    get_ad_sets,
    _batch_insights,
    aggregate_windows_from_rows,
    infer_audience_type,
    _ensure_act_prefix,
    get_sync_lock,
)
from app.utils.cache import (
    cache_invalidate_prefix,
    PREFIX_AUDIENCES,
    PREFIX_RECOMMENDATIONS,
    PREFIX_BENCHMARKS,
    PREFIX_METRICS,
)
from app.utils.crypto import decrypt_token

logger = logging.getLogger(__name__)

# Valid Meta date presets
VALID_DATE_PRESETS = {
    "yesterday", "last_3d", "last_7d", "last_14d", "last_28d", "last_30d",
    "last_90d", "this_month", "last_month", "this_quarter", "last_quarter",
    "this_year", "last_year", "maximum", "data_maximum",
}


@dataclass
class SyncJobState:
    account_id: str
    date_preset: str
    status: str = "idle"  # idle | in_progress | completed | failed | cancelled
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: dict[str, Any] | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


_sync_jobs: dict[str, SyncJobState] = {}
_sync_jobs_lock = threading.Lock()


def _get_or_create_job(account_id: str, date_preset: str = "last_7d") -> SyncJobState:
    with _sync_jobs_lock:
        job = _sync_jobs.get(account_id)
        if job is None:
            job = SyncJobState(account_id=account_id, date_preset=date_preset)
            _sync_jobs[account_id] = job
        return job


def get_sync_job_status(account_id: str) -> dict[str, Any]:
    with _sync_jobs_lock:
        job = _sync_jobs.get(account_id)
        if not job:
            return {
                "status": "idle",
                "message": None,
                "started_at": None,
                "finished_at": None,
                "summary": None,
                "date_preset": None,
            }
        return {
            "status": job.status,
            "message": job.message,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "summary": job.summary,
            "date_preset": job.date_preset,
        }


def request_cancel_sync(account_id: str) -> dict[str, Any]:
    with _sync_jobs_lock:
        job = _sync_jobs.get(account_id)
        if not job or job.status != "in_progress":
            return {"status": "idle", "message": "No active sync to cancel."}
        job.cancel_event.set()
        job.message = "Cancellation requested. Waiting for current API step to stop."
        return {"status": "cancelling", "message": job.message}


def start_sync_job(account_id: str, date_preset: str = "last_7d") -> dict[str, Any]:
    if date_preset not in VALID_DATE_PRESETS:
        date_preset = "last_7d"

    with _sync_jobs_lock:
        existing = _sync_jobs.get(account_id)
        if existing and existing.status == "in_progress":
            return {
                "status": "in_progress",
                "message": "Sync already in progress for this account.",
            }

        job = SyncJobState(
            account_id=account_id,
            date_preset=date_preset,
            status="in_progress",
            started_at=datetime.now(timezone.utc),
            message="Sync started",
        )
        _sync_jobs[account_id] = job

    thread = threading.Thread(
        target=_run_sync_job,
        args=(account_id, date_preset),
        name=f"sync-{account_id}",
        daemon=True,
    )
    thread.start()
    return {
        "status": "in_progress",
        "message": "Sync started",
        "started_at": job.started_at.isoformat() if job.started_at else None,
    }


def _set_job_result(account_id: str, status: str, message: str | None, summary: dict[str, Any] | None) -> None:
    with _sync_jobs_lock:
        job = _sync_jobs.get(account_id)
        if not job:
            return
        job.status = status
        job.message = message
        job.summary = summary
        job.finished_at = datetime.now(timezone.utc)


def _run_sync_job(account_id: str, date_preset: str) -> None:
    db = SessionLocal()
    try:
        summary = sync_account(account_id, db, date_preset=date_preset)
        if summary.get("cancelled"):
            _set_job_result(account_id, "cancelled", "Sync cancelled by user", summary)
            return
        if summary.get("errors"):
            _set_job_result(account_id, "failed", "Sync finished with errors", summary)
            return
        _set_job_result(account_id, "completed", "Sync completed", summary)
    except Exception as e:
        logger.exception("Background sync failed for %s", account_id)
        _set_job_result(account_id, "failed", str(e), {"errors": [str(e)]})
    finally:
        db.close()


def _is_cancelled(account_id: str) -> bool:
    with _sync_jobs_lock:
        job = _sync_jobs.get(account_id)
        return bool(job and job.cancel_event.is_set())


def _ensure_not_cancelled(account_id: str) -> None:
    if _is_cancelled(account_id):
        raise RuntimeError("Sync cancelled by user")


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
    Uses batch API to fetch insights for all ad sets in chunks, then
    aggregates into 1d/3d/7d windows locally.
    """
    if date_preset not in VALID_DATE_PRESETS:
        date_preset = "last_7d"

    lock = get_sync_lock(account_id)
    if not lock.acquire(blocking=False):
        logger.warning("Sync already in progress for account %s, skipping", account_id)
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
    logger.info("Syncing account %s (%s) with preset=%s", account.account_name, meta_id, date_preset)

    summary = {
        "audiences_created": 0,
        "audiences_updated": 0,
        "snapshots_created": 0,
        "errors": [],
        "cancelled": False,
    }

    try:
        _ensure_not_cancelled(account_id)
        with httpx.Client(http2=False) as client:
            ad_sets_data = get_ad_sets(client, token, meta_id)
            logger.info("Fetched %d ad sets from Meta", len(ad_sets_data))

            _ensure_not_cancelled(account_id)
            ad_set_id_to_audience: dict[str, Audience] = {}
            for ad_set_data in ad_sets_data:
                _ensure_not_cancelled(account_id)
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

            _ensure_not_cancelled(account_id)
            ad_set_ids = list(ad_set_id_to_audience.keys())
            logger.info("Batch-fetching insights for %d ad sets (preset=%s)", len(ad_set_ids), date_preset)
            all_daily_rows = _batch_insights(client, token, ad_set_ids, date_preset)

            today = date.today()
            for meta_ad_set_id, daily_rows in all_daily_rows.items():
                _ensure_not_cancelled(account_id)
                audience = ad_set_id_to_audience.get(meta_ad_set_id)
                if not audience or not daily_rows:
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
                        db.add(MetricSnapshot(
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
                        ))
                        summary["snapshots_created"] += 1

            account.last_synced_at = datetime.now(timezone.utc)
            db.commit()

            total = 0
            total += cache_invalidate_prefix(PREFIX_AUDIENCES)
            total += cache_invalidate_prefix(PREFIX_RECOMMENDATIONS)
            total += cache_invalidate_prefix(PREFIX_BENCHMARKS)
            total += cache_invalidate_prefix(PREFIX_METRICS)
            logger.info("Post-sync cache invalidation: %d keys cleared", total)

    except RuntimeError as e:
        if "cancelled" in str(e).lower():
            db.rollback()
            summary["cancelled"] = True
            return summary
        raise
    except Exception as e:
        db.rollback()
        logger.error("Sync failed: %s", e, exc_info=True)
        summary["errors"].append(str(e))

    logger.info(
        "Sync complete: %s created, %s updated, %s snapshots, %s errors",
        summary["audiences_created"],
        summary["audiences_updated"],
        summary["snapshots_created"],
        len(summary["errors"]),
    )
    return summary
