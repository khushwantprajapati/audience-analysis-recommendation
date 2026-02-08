"""Generated recommendation per audience (rule engine + Claude)."""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audience import Audience


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    audience_id: Mapped[str] = mapped_column(String(36), ForeignKey("audiences.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(32))  # SCALE, HOLD, PAUSE, RETEST
    scale_percentage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16))  # HIGH, MEDIUM, LOW
    performance_bucket: Mapped[str] = mapped_column(String(32))  # WINNER, AVERAGE, LOSER
    trend_state: Mapped[str] = mapped_column(String(32))  # STABLE, IMPROVING, DECLINING, VOLATILE
    composite_score: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    reasons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # list of strings
    risks: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # list of strings
    metrics_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    audience: Mapped["Audience"] = relationship("Audience", back_populates="recommendations")

    def __repr__(self) -> str:
        return f"<Recommendation audience={self.audience_id} action={self.action}>"
