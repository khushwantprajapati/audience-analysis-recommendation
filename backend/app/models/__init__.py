"""SQLAlchemy models - import all so Base.metadata creates tables."""
from app.database import Base
from app.models.account import Account
from app.models.audience import Audience
from app.models.metric_snapshot import MetricSnapshot
from app.models.recommendation import Recommendation
from app.models.action_log import ActionLog

__all__ = [
    "Base",
    "Account",
    "Audience",
    "MetricSnapshot",
    "Recommendation",
    "ActionLog",
]
