"""Declarative base + shared mixins for the PostgreSQL schema (Phase 1).

No hard-coded database credentials anywhere in this package — see `session.py`
for how the connection string is resolved from environment variables only.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in this package."""


class TimestampMixin:
    """created_at/updated_at on every table that needs them (Phase 1 requirement)."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
