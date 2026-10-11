"""SQLAlchemy ORM models (PRD FR-7: persist runs, listings, providers).

Tables are created on startup via `Base.metadata.create_all` (no migrations
for the MVP), so this module must be imported before create_all runs.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SearchRun(Base):
    """One executed search for a normalized (language, location) pair."""

    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    language: Mapped[str] = mapped_column(String(64), index=True)
    location: Mapped[str] = mapped_column(String(120), index=True)
    source: Mapped[str] = mapped_column(String(16), default="live")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    explicit_count: Mapped[int] = mapped_column(Integer, default=0)
    inferred_count: Mapped[int] = mapped_column(Integer, default=0)

    listings: Mapped[list[Listing]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    providers: Mapped[list[Provider]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Listing(Base):
    """A scored job listing attached to a search run (FR-4..FR-8)."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id"), index=True)
    title: Mapped[str] = mapped_column(String(400))
    company: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    salary_text: Mapped[str | None] = mapped_column(String(120))
    posted_days_ago: Mapped[int | None] = mapped_column(Integer)
    snippet: Mapped[str | None] = mapped_column(Text)
    apply_link: Mapped[str] = mapped_column(String(800))
    source_name: Mapped[str | None] = mapped_column(String(200))
    relevance_label: Mapped[str] = mapped_column(String(32))
    relevance_score: Mapped[float] = mapped_column(Float)
    matched_terms: Mapped[str] = mapped_column(Text, default="[]")
    trust_hints: Mapped[str] = mapped_column(Text, default="[]")

    run: Mapped[SearchRun] = relationship(back_populates="listings")


class Provider(Base):
    """A Google Maps language-service provider attached to a run (FR-12)."""

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(400))
    rating: Mapped[float | None] = mapped_column(Float)
    website: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(50))

    run: Mapped[SearchRun] = relationship(back_populates="providers")


class ApiCall(Base):
    """Daily SerpApi call counter row (one row per day, FR-7 budget)."""

    __tablename__ = "api_calls"

    day: Mapped[datetime] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
