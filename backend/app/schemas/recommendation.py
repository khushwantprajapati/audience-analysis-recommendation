from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MetricsSnapshotSchema(BaseModel):
    roas: Optional[float] = None
    cpa: Optional[float] = None
    spend: Optional[float] = None
    revenue: Optional[float] = None
    purchases: Optional[int] = None
    cvr: Optional[float] = None
    clicks: Optional[int] = None
    impressions: Optional[int] = None


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    audience_id: str
    audience_name: Optional[str] = None
    audience_type: Optional[str] = None
    action: str
    scale_percentage: Optional[int] = None
    confidence: str
    performance_bucket: str
    trend_state: str
    composite_score: Optional[float] = None
    reasons: Optional[list[str]] = None
    risks: Optional[list[str]] = None
    metrics_snapshot: Optional[dict] = None
    generated_at: datetime
