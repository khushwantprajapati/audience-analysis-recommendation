"""Time-series performance data per audience (per date + window)."""
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.audience import Audience


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    audience_id: Mapped[str] = mapped_column(String(36), ForeignKey("audiences.id", ondelete="CASCADE"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    window_days: Mapped[int] = mapped_column()  # 1, 3, or 7
    spend: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    purchases: Mapped[int] = mapped_column(default=0)
    impressions: Mapped[int] = mapped_column(default=0)
    clicks: Mapped[int] = mapped_column(default=0)
    ctr: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)
    cpc: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    roas: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)  # revenue / spend
    cpa: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)  # spend / purchases
    cvr: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)  # purchases / clicks
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    audience: Mapped["Audience"] = relationship("Audience", back_populates="metric_snapshots")

    def __repr__(self) -> str:
        return f"<MetricSnapshot audience={self.audience_id} date={self.snapshot_date} window={self.window_days}d>"
