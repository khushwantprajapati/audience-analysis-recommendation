from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AudienceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    account_id: str
    meta_ad_set_id: str
    name: str
    audience_type: str
    lookalike_pct: Optional[float] = None
    source_quality: Optional[str] = None
    launched_at: Optional[datetime] = None
    current_budget: Optional[Decimal] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AudienceDetail(AudienceResponse):
    pass
