"""Account CRUD and list."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account
from app.schemas import AccountResponse, AccountList

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountList)
def list_accounts(db: Session = Depends(get_db)):
    """List all connected Meta ad accounts."""
    accounts = db.query(Account).order_by(Account.created_at.desc()).all()
    return AccountList(accounts=[AccountResponse.model_validate(a) for a in accounts])


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: str, db: Session = Depends(get_db)):
    """Get one account by id."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountResponse.model_validate(account)
