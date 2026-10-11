"""Search orchestration (PRD FR-2..FR-8, FR-11, FR-15/16).

Flow per section 9: validate -> cache check -> budget check -> live calls ->
parse/score/dedupe/filter -> store -> respond. Stages 3-5 fail soft: with no
reachable Postgres or no budget the sealed fixtures / seeded payloads serve.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.core.data_loader import TRUST_NOTICE, normalize_location, resolve_city, resolve_language
from app.core.providers import (
    PROVIDERS_LABEL,
    build_provider_queries,
    load_filters,
    select_providers,
)
from app.core.scoring import EXPLICIT, load_keywords, score_listing
from app.core.trust_hints import detect_trust_hints
from app.db import repo

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"
ROLE_TERMS = "translator OR interpreter OR transcription"

HL_BY_ID = {
    "hindi": "hi",
    "tamil": "ta",
    "bengali": "bn",
    "maithili": "hi",
    "bhojpuri": "hi",
    "telugu": "te",
    "marathi": "mr",
    "gujarati": "gu",
}

MAX_PAGES = 2  # FR-3
MAX_POSTED_DAYS = 30  # FR-8
SALARY_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s?[\d,]+(?:\s?[-\u2013]\s?(?:₹|rs\.?|inr)?\s?[\d,]+)?",
    re.IGNORECASE,
)


def _posted_days(ext) -> int | None:
    for s in ext or []:
        m = re.search(r"(\d+)\s*day", str(s))
        if m:
            return int(m.group(1))
    return None


def _salary_text(item: dict) -> str | None:
    """FR-5: salary from the structured field, else the first ₹/Rs mention."""
    ext = item.get("detected_extensions") or {}
    if isinstance(ext, dict):
        s = ext.get("salary")
        if isinstance(s, str) and s.strip():
            return s.strip()
    m = SALARY_RE.search(str(item.get("description") or ""))
    return m.group(0).strip() if m else None


def _parse_job(item: dict) -> dict:
    ao = item.get("apply_options") or []
    link = ao[0].get("link") if ao and isinstance(ao[0], dict) else None
    return {
        "title": item.get("title"),
        "company": item.get("company_name"),
        "location": item.get("location"),
        "salary_text": _salary_text(item),
        "snippet": item.get("description"),
        "posted_days_ago": _posted_days(item.get("extensions")),
        "apply_link": link or item.get("source_link"),
        "source_name": item.get("via"),
    }


def _fingerprint(parsed: dict) -> str:
    """FR-6: dedupe key = apply link, else hash of (company, title, location)."""
    link = (parsed.get("apply_link") or "").strip().lower()
    if link:
        return "link:" + link
    key = "|".join(
        str(parsed.get(f) or "").strip().lower() for f in ("company", "title", "location")
    )
    return "hash:" + hashlib.sha1(key.encode("utf-8")).hexdigest()


def _demo_payload(lang_id: str, city_id: str, budget: int) -> dict | None:
    p = FIXTURES_DIR / f"search_{lang_id}_{city_id}.json"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not isinstance(doc, dict) or "listings" not in doc:
        return None
    doc.setdefault("meta", {})["source"] = "fallback"
    doc["meta"]["daily_budget_remaining"] = budget
    vis = {"explicit": 0, "inferred": 0}
    for item in doc.get("listings") or []:
        key = "explicit" if item.get("relevance_label") == EXPLICIT else "inferred"
        vis[key] += 1
    doc["meta"]["visibility"] = vis
    doc.setdefault("notice", TRUST_NOTICE)
    return doc


def _score_key(t):
    return -t[0].score


def _assemble(lang_id, lang_name, city_disp, items, raw_places, budget, source):
    kw = load_keywords(lang_id, data_dir=REPO_ROOT / "data" / "keywords")
    pairs = []
    seen = set()
    for it in items:
        parsed = _parse_job(it)
        age = parsed.get("posted_days_ago")
        if age is not None and age > MAX_POSTED_DAYS:
            continue  # FR-8
        if not parsed.get("title") or not parsed.get("apply_link"):
            continue  # FR-5
        fp = _fingerprint(parsed)
        if fp in seen:
            continue  # FR-6
        seen.add(fp)
        s = score_listing(parsed, kw, city_disp)
        if s is not None:
            pairs.append((s, parsed))
    pairs.sort(key=_score_key)
    out_listings = []
    exp = inf = 0
    for s, parsed in pairs:
        if s.label == EXPLICIT:
            exp += 1
        else:
            inf += 1
        out_listings.append(
            {
                "title": parsed.get("title") or "",
                "company": parsed.get("company"),
                "location": parsed.get("location"),
                "salary_text": parsed.get("salary_text"),
                "posted_days_ago": parsed.get("posted_days_ago"),
                "snippet": (parsed.get("snippet") or "")[:600] or None,
                "apply_link": parsed.get("apply_link") or "",
                "source_name": parsed.get("source_name"),
                "relevance_label": s.label,
                "relevance_score": float(s.score),
                "matched_terms": list(s.matched_terms),
                "trust_hints": detect_trust_hints(parsed),
            }
        )
    filt = load_filters(REPO_ROOT / "data" / "provider_filters.json")
    kept = select_providers(raw_places or [], filt)
    providers = []
    for p in kept[:8]:
        providers.append(
            {
                "name": p.get("name") or "",
                "category": p.get("category"),
                "address": p.get("address"),
                "rating": p.get("rating"),
                "website": p.get("website"),
                "phone": p.get("phone"),
            }
        )
    now = datetime.now(UTC).isoformat()
    return {
        "meta": {
            "source": source,
            "fetched_at": now,
            "daily_budget_remaining": budget,
            "visibility": {"explicit": exp, "inferred": inf},
        },
        "listings": out_listings,
        "providers": providers,
        "providers_label": PROVIDERS_LABEL.format(city=city_disp),
        "notice": TRUST_NOTICE,
    }


def _live(lang_id, lang_name, hl, city_disp, lat, lng, budget):
    """Live SerpApi run (Jobs then Maps). Returns (payload, calls_made)."""
    from scripts.spike_serpapi import SerpApiClient

    settings = get_settings()
    key = settings.serpapi_key or ""
    client = SerpApiClient(key, timeout=float(settings.serpapi_timeout_seconds or 20.0))
    items = []
    raw_places = []
    calls = 0
    try:
        token = None
        for _ in range(MAX_PAGES):
            params = {
                "q": lang_name + " " + ROLE_TERMS,
                "location": city_disp + ", India",
                "gl": "in",
                "hl": hl,
            }
            if token:
                params["next_page_token"] = token
            try:
                page = client.get("google_jobs", params)
                calls += 1
            except Exception:
                break
            items.extend(page.get("jobs_results") or [])
            token = (page.get("serpapi_pagination") or {}).get("next_page_token")
            if not token:
                break
        filt = load_filters(REPO_ROOT / "data" / "provider_filters.json")
        for q in build_provider_queries(lang_name, city_disp, filt)[:2]:
            try:
                doc = client.get(
                    "google_maps",
                    {"q": q, "ll": "@" + str(lat) + "," + str(lng) + ",12z", "gl": "in", "hl": hl},
                )
                calls += 1
            except Exception:
                continue
            raw_places.extend(doc.get("local_results") or [])
    finally:
        with contextlib.suppress(Exception):
            client.close()
    payload = _assemble(lang_id, lang_name, city_disp, items, raw_places, budget, "live")
    return payload, calls


def _fallback_from_raw(lang_id, city_id, lang_name, city_disp, budget):
    raw_p = FIXTURES_DIR / ("raw_search_" + lang_id + "_" + city_id + ".json")
    try:
        doc = json.loads(raw_p.read_text(encoding="utf-8"))
    except OSError:
        return None
    items = []
    for pg in doc.get("pages") or []:
        items.extend(pg.get("jobs_results") or [])
    if not items:
        return None
    cmap = {"delhi-ncr": "delhi_ncr", "chennai": "chennai", "kolkata": "kolkata"}
    ckey = cmap.get(city_id, city_id)
    raws = []
    mp = FIXTURES_DIR / ("maps_" + ckey + ".json")
    try:
        mdoc = json.loads(mp.read_text(encoding="utf-8"))
    except OSError:
        mdoc = {}
    for _q, qdoc in (mdoc.get("queries") or {}).items():
        raws.extend(qdoc.get("local_results") or [])
    payload = _assemble(lang_id, lang_name, city_disp, items, raws, budget, "fallback")
    return payload, 0


def _cached_payload(cached, budget, city_disp):
    vis = cached.get("visibility") or {
        "explicit": cached.get("explicit", 0),
        "inferred": cached.get("inferred", 0),
    }
    return {
        "meta": {
            "source": "cache",
            "fetched_at": cached["fetched_at"],
            "daily_budget_remaining": budget,
            "visibility": vis,
        },
        "listings": cached.get("listings") or [],
        "providers": cached.get("providers") or [],
        "providers_label": PROVIDERS_LABEL.format(city=city_disp),
        "notice": TRUST_NOTICE,
    }


def _degraded(lang_id, lang_name, city_disp, city_id, seeded, budget):
    """Sealed-fixture chain used whenever live calls are impossible (FR-15)."""
    if seeded is not None:
        return seeded
    fb = _fallback_from_raw(lang_id, city_id, lang_name, city_disp, budget)
    if fb is not None:
        return fb[0]
    return _assemble(lang_id, lang_name, city_disp, [], [], budget, "fallback")


def run_search(language, location):
    settings = get_settings()
    cap = int(settings.serpapi_daily_cap or 0)
    budget = repo.budget_remaining(cap)
    lang = resolve_language(language)
    if lang is None:
        return None
    lang_id = str(lang.get("id"))
    lang_name = str(lang.get("name"))
    city = resolve_city(location)
    city_id = str(city.get("id")) if city else location.strip().lower().replace(" ", "-")
    city_disp = str(city.get("display_name")) if city else normalize_location(location)
    seeded = _demo_payload(lang_id, city_id, budget)
    if settings.demo_mode or not settings.serpapi_key:
        return _degraded(lang_id, lang_name, city_disp, city_id, seeded, budget)

    cached = repo.find_cached_run(lang_id, city_disp)
    if cached is not None:
        return _cached_payload(cached, budget, city_disp)
    if budget <= 0:
        # Daily cap reached: never call upstream, serve sealed data (FR-11).
        return _degraded(lang_id, lang_name, city_disp, city_id, seeded, budget)

    lat = city.get("lat") if city else 28.6139
    lng = city.get("lng") if city else 77.209
    try:
        payload, calls = _live(
            lang_id, lang_name, HL_BY_ID.get(lang_id, "en"), city_disp, lat, lng, budget
        )
    except Exception:
        return _degraded(lang_id, lang_name, city_disp, city_id, seeded, budget)
    payload["meta"]["daily_budget_remaining"] = max(budget - calls, 0)
    repo.save_run(lang_id, city_disp, payload, calls)
    return payload
