"""SQLAlchemy declarative base and shared column types."""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, mapped_column

__all__ = ["Base", "utcnow", "timestamp_column"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_column(**kwargs):
    """Timezone-aware timestamp. Postgres stores UTC; we never store naive."""
    return mapped_column(DateTime(timezone=True), default=utcnow, **kwargs)


class Base(DeclarativeBase):
    pass
