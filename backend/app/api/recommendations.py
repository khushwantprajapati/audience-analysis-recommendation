"""Trigger and fetch recommendations."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Audience, Recommendation
from app.schemas import RecommendationResponse

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationResponse])
def list_recommendations(
    account_id: str = Query(..., description="Account ID"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List latest recommendations for an account's audiences."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    recs = (
        db.query(Recommendation)
        .join(Audience)
        .filter(Audience.account_id == account_id)
        .order_by(Recommendation.generated_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for r in recs:
        data = RecommendationResponse.model_validate(r)
        data.audience_name = r.audience.name
        data.audience_type = r.audience.audience_type
        out.append(data)
    return out


@router.post("/generate")
async def generate_recommendations(
    account_id: str = Query(..., description="Account ID"),
    db: Session = Depends(get_db),
):
    """Trigger recommendation generation (rules -> Claude), then return new recommendations."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    from app.services.claude_analyzer import generate_recommendations_for_account
    try:
        results = generate_recommendations_for_account(db, account_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"recommendations": results, "count": len(results)}
