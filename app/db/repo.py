"""Repository helpers for the 24h cache and the daily budget counter (FR-7).

Every helper fails soft: if Postgres is unreachable (no `DATABASE_URL`,
offline demo), callers fall back to seeded fixtures instead of erroring.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.base import Base
from app.db.models import ApiCall, Listing, Provider, SearchRun
from app.db.session import SessionLocal, engine

CACHE_TTL_HOURS = 24


def db_available() -> bool:
    """True when the database answers a trivial query."""
    try:
        with SessionLocal() as session:
            session.execute(select(func.count()).select_from(ApiCall))
        return True
    except SQLAlchemyError:
        return False


def init_db() -> bool:
    """Create tables if missing. Returns True when the schema is ready."""
    # Imported for side effect: models must register on Base before create_all.
    from app.db import models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
        return True
    except SQLAlchemyError:
        return False


def budget_remaining(cap: int) -> int:
    """Remaining SerpApi calls for today: cap minus today's counted calls."""
    try:
        with SessionLocal() as session:
            row = session.get(ApiCall, date.today())
            used = int(row.count) if row else 0
    except SQLAlchemyError:
        return cap
    return max(cap - used, 0)


def record_calls(n: int) -> None:
    """Add `n` calls to today's counter (best effort)."""
    if n <= 0:
        return
    try:
        with SessionLocal() as session:
            row = session.get(ApiCall, date.today())
            if row is None:
                row = ApiCall(day=date.today(), count=0)
                session.add(row)
            row.count += n
            session.commit()
    except SQLAlchemyError:
        pass


def find_cached_run(language: str, location: str) -> dict | None:
    """Return the newest run for the pair within the 24h TTL, or None."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=CACHE_TTL_HOURS)
    try:
        with SessionLocal() as session:
            run = session.scalar(
                select(SearchRun)
                .where(
                    SearchRun.language == language,
                    SearchRun.location == location,
                    SearchRun.fetched_at >= cutoff,
                )
                .order_by(SearchRun.fetched_at.desc())
            )
            if run is None:
                return None
            listings = [
                {
                    "title": item.title,
                    "company": item.company,
                    "location": item.location,
                    "salary_text": item.salary_text,
                    "posted_days_ago": item.posted_days_ago,
                    "snippet": item.snippet,
                    "apply_link": item.apply_link,
                    "source_name": item.source_name,
                    "relevance_label": item.relevance_label,
                    "relevance_score": float(item.relevance_score),
                    "matched_terms": json.loads(item.matched_terms or "[]"),
                    "trust_hints": json.loads(item.trust_hints or "[]"),
                }
                for item in run.listings
            ]
            providers = [
                {
                    "name": p.name,
                    "category": p.category,
                    "address": p.address,
                    "rating": float(p.rating) if p.rating is not None else None,
                    "website": p.website,
                    "phone": p.phone,
                }
                for p in run.providers
            ]
            return {
                "fetched_at": run.fetched_at.replace(tzinfo=UTC).isoformat(),
                "listings": listings,
                "providers": providers,
                "explicit": int(run.explicit_count),
                "inferred": int(run.inferred_count),
            }
    except SQLAlchemyError:
        return None


def save_run(
    language: str,
    location: str,
    payload: dict,
    calls_made: int,
) -> None:
    """Persist a completed search run (listings + providers) and count calls."""
    try:
        with SessionLocal() as session:
            meta = payload.get("meta") or {}
            vis = meta.get("visibility") or {}
            run = SearchRun(
                language=language,
                location=location,
                source=str(meta.get("source") or "live"),
                explicit_count=int(vis.get("explicit") or 0),
                inferred_count=int(vis.get("inferred") or 0),
            )
            for item in payload.get("listings") or []:
                run.listings.append(
                    Listing(
                        title=item.get("title") or "",
                        company=item.get("company"),
                        location=item.get("location"),
                        salary_text=item.get("salary_text"),
                        posted_days_ago=item.get("posted_days_ago"),
                        snippet=item.get("snippet"),
                        apply_link=item.get("apply_link") or "",
                        source_name=item.get("source_name"),
                        relevance_label=item.get("relevance_label") or "",
                        relevance_score=float(item.get("relevance_score") or 0.0),
                        matched_terms=json.dumps(item.get("matched_terms") or []),
                        trust_hints=json.dumps(item.get("trust_hints") or []),
                    )
                )
            for p in payload.get("providers") or []:
                run.providers.append(
                    Provider(
                        name=p.get("name") or "",
                        category=p.get("category"),
                        address=p.get("address"),
                        rating=p.get("rating"),
                        website=p.get("website"),
                        phone=p.get("phone"),
                    )
                )
            session.add(run)
            session.commit()
    except SQLAlchemyError:
        return
    record_calls(calls_made)
