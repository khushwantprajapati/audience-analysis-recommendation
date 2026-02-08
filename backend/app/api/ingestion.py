"""Data ingestion: sync ad set data from Meta."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account
from app.services.ingestion import sync_account as run_sync

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/sync/{account_id}")
async def sync_account(account_id: str, db: Session = Depends(get_db)):
    """Pull ad set data from Meta API and store."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    result = run_sync(account_id, db)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
