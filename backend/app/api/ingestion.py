"""Data ingestion: sync ad set data from Meta."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account
from app.services.ingestion import (
    start_sync_job,
    get_sync_job_status,
    request_cancel_sync,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/sync/{account_id}")
async def sync_account(
    account_id: str,
    date_preset: str = Query("last_7d", description="Meta date preset: last_7d, last_14d, last_30d, etc."),
    db: Session = Depends(get_db),
):
    """Start account sync in background and return job status."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return start_sync_job(account_id, date_preset)


@router.get("/sync/{account_id}/status")
async def sync_status(account_id: str, db: Session = Depends(get_db)):
    """Get sync job status for account."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return get_sync_job_status(account_id)


@router.post("/sync/{account_id}/cancel")
async def cancel_sync(account_id: str, db: Session = Depends(get_db)):
    """Request cancellation for an in-progress sync."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return request_cancel_sync(account_id)
