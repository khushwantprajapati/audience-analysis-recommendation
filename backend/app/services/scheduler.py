"""APScheduler: periodic sync and outcome logging."""
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import Account, ActionLog, Audience, MetricSnapshot
from app.services.ingestion import sync_account
from app.services.metrics import compute_audience_metrics, get_account_benchmarks


def _sync_all_accounts() -> None:
    db = SessionLocal()
    try:
        for account in db.query(Account).all():
            try:
                sync_account(account.id, db)
            except Exception:
                pass
    finally:
        db.close()


def _update_outcome_metrics() -> None:
    """Backfill outcome_3d_metrics and outcome_7d_metrics for ActionLog rows that are old enough."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        three_days_ago = now - timedelta(days=3)
        seven_days_ago = now - timedelta(days=7)
        logs_3d = (
            db.query(ActionLog)
            .filter(ActionLog.created_at <= three_days_ago, ActionLog.outcome_3d_metrics.is_(None))
            .limit(100)
            .all()
        )
        for log in logs_3d:
            try:
                metrics = compute_audience_metrics(db, log.audience_id, account_id=log.account_id)
                if metrics:
                    log.outcome_3d_metrics = {
                        "roas": metrics.get("roas"),
                        "cpa": metrics.get("cpa"),
                        "spend": metrics.get("spend"),
                        "purchases": metrics.get("purchases"),
                    }
                    log.outcome_3d_at = now
            except Exception:
                pass
        logs_7d = (
            db.query(ActionLog)
            .filter(ActionLog.created_at <= seven_days_ago, ActionLog.outcome_7d_metrics.is_(None))
            .limit(100)
            .all()
        )
        for log in logs_7d:
            try:
                metrics = compute_audience_metrics(db, log.audience_id, account_id=log.account_id)
                if metrics:
                    log.outcome_7d_metrics = {
                        "roas": metrics.get("roas"),
                        "cpa": metrics.get("cpa"),
                        "spend": metrics.get("spend"),
                        "purchases": metrics.get("purchases"),
                    }
                    log.outcome_7d_at = now
            except Exception:
                pass
        db.commit()
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(_sync_all_accounts, IntervalTrigger(hours=6), id="sync_accounts")
    scheduler.add_job(_update_outcome_metrics, IntervalTrigger(hours=12), id="outcome_metrics")
    scheduler.start()
    return scheduler
