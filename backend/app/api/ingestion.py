"""Data ingestion: sync ad set data from Meta."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account
from app.services.ingestion import sync_account as run_sync

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/sync/{account_id}")
async def sync_account(
    account_id: str,
    date_preset: str = Query("last_7d", description="Meta date preset: last_7d, last_14d, last_30d, etc."),
    db: Session = Depends(get_db),
):
    """Pull ad set data from Meta API and store."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    result = run_sync(account_id, db, date_preset=date_preset)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
