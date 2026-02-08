"""Meta ad account + OAuth tokens."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meta_account_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str] = mapped_column(Text)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    audiences: Mapped[list["Audience"]] = relationship("Audience", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Account {self.account_name or self.meta_account_id}>"
