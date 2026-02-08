"""Audience (ad set) metadata."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.metric_snapshot import MetricSnapshot
    from app.models.recommendation import Recommendation


class Audience(Base):
    __tablename__ = "audiences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    meta_ad_set_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512))
    audience_type: Mapped[str] = mapped_column(String(32))  # BROAD, INTEREST, LLA, CUSTOM
    lookalike_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    source_quality: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # Purchasers, ATC, VC
    launched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    campaign_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    account: Mapped["Account"] = relationship("Account", back_populates="audiences")
    metric_snapshots: Mapped[list["MetricSnapshot"]] = relationship(
        "MetricSnapshot", back_populates="audience", cascade="all, delete-orphan", order_by="MetricSnapshot.snapshot_date"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        "Recommendation", back_populates="audience", cascade="all, delete-orphan", order_by="Recommendation.generated_at.desc()"
    )

    def __repr__(self) -> str:
        return f"<Audience {self.name}>"
