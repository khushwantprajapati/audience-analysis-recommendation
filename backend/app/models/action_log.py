"""Historical log of recommendations for feedback loop."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    audience_id: Mapped[str] = mapped_column(String(36), index=True)  # may outlive audience
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    input_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    decision: Mapped[str] = mapped_column(String(32))  # SCALE, HOLD, PAUSE, RETEST
    confidence: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reasons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    outcome_3d_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    outcome_7d_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    outcome_3d_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_7d_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ActionLog audience={self.audience_id} decision={self.decision}>"
