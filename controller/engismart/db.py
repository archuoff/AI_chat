"""Database access of Engismart: the platform's own engine and database (models/model.py), nothing of ours.

The only table Engismart owns is `tbl_engismart_image` (class EngismartImage in the platform's models/orm_models.py).
Users, roles, application rows, audit log and usage rows are the platform's tables (see access.py, usage_log.py)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from models.model import engine

# Same engine and connection pool as the rest of the platform; objects stay readable after commit (expire_on_commit=False).
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    """ISO-8601 with an explicit UTC offset (MySQL and SQLite return naive datetimes; browsers would read them as local time)."""
    if dt is None:
        return None
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).isoformat()
