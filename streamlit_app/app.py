# streamlit_app/app.py
"""Streamlit skeleton for Language Opportunity Radar (PRD v1.2).

Runs against the FastAPI backend (API_URL), or against the saved fixture when
DEMO_MODE=1 or the API is unreachable, so it works with no API key.

Run:  streamlit run streamlit_app/app.py

All scraped text (titles, companies, snippets, provider fields) is rendered as
plain text via st.text, never as markdown/HTML. Only http/https links are shown.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"
REPORT_EMAIL = os.getenv("REPORT_EMAIL", "report@example.com")
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "search_tamil_chennai.json"
FALLBACK_LANGUAGES = ["Hindi", "Tamil", "Bengali", "Maithili", "Bhojpuri"]
SOURCE_BADGE = {"cache": "Cache hit", "live": "Live call", "fallback": "Fallback (saved data)"}

st.set_page_config(page_title="Language Opportunity Radar", layout="wide")


def http_url(url: str | None) -> str | None:
    if url and urlparse(url).scheme in ("http", "https"):
        return url
    return None


def load_fixture() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.setdefault("meta", {})["source"] = "fallback"
    return data


@st.cache_data(ttl=300)
def get_languages() -> list[str]:
    if DEMO_MODE:
        return FALLBACK_LANGUAGES
    try:
        r = requests.get(f"{API_URL}/api/languages", timeout=5)
        r.raise_for_status()
        data = r.json()
        langs = data.get("languages", data) if isinstance(data, dict) else data
        return [
            item if isinstance(item, str) else item.get("name", "") for item in langs
        ] or FALLBACK_LANGUAGES
    except Exception:
        return FALLBACK_LANGUAGES


def run_search(language: str, location: str, pin: str) -> tuple[dict, str | None]:
    """Returns (payload, user_message). Never shows raw upstream errors."""
    if DEMO_MODE:
        return load_fixture(), "Demo mode: showing saved sample results."
    body = {"language": language, "location": location}
    if pin:
        body["pin_code"] = pin
    try:
        r = requests.post(f"{API_URL}/api/search", json=body, timeout=15)
        if r.status_code == 429:
            return load_fixture(), "Too many searches right now. Showing saved results."
        if r.status_code == 422:
            return {}, "Please check your inputs and try again."
        r.raise_for_status()
        return r.json(), None
    except Exception:
        return load_fixture(), "Search is unavailable right now. Showing saved results."


def sort_listings(listings: list[dict], key: str) -> list[dict]:
    if key == "Posted date":
        return sorted(
            listings,
            key=lambda item: (
                item.get("posted_days_ago") if item.get("posted_days_ago") is not None else 999
            ),
        )
    if key == "Location":
        return sorted(listings, key=lambda item: (item.get("location") or "").casefold())
    return sorted(listings, key=lambda item: -(item.get("relevance_score") or 0))


def render_listing(item: dict, idx: int) -> None:
    with st.container(border=True):
        st.text(item.get("title", ""))
        st.text(
            " · ".join(
                x for x in [item.get("company"), item.get("location"), item.get("salary_text")] if x
            )
        )
        st.caption(item.get("relevance_label", ""))
        chips = item.get("matched_terms") or []
        if chips:
            st.text("Evidence: " + " · ".join(chips))
        for hint in item.get("trust_hints") or []:
            st.text(hint)
        if item.get("snippet"):
            st.text(item["snippet"])
        age = item.get("posted_days_ago")
        meta = f"Posted {age} days ago" if age is not None else "Posted date unknown"
        st.text(f"{meta} · Source: {item.get('source_name', '')}")
        link = http_url(item.get("apply_link"))
        if link:
            st.link_button("Apply at source", link, key=f"apply_{idx}")
        st.markdown(f"[Report this listing](mailto:{REPORT_EMAIL}?subject=Report%20listing)")


def render_providers(providers: list[dict], city: str) -> None:
    st.caption(f"Providers in {city}. Confirm language availability directly.")
    if not providers:
        st.text("No providers found for this search.")
    for i, p in enumerate(providers):
        with st.container(border=True):
            st.text(p.get("name", ""))
            st.text(" · ".join(x for x in [p.get("category"), p.get("address")] if x))
            bits = []
            if p.get("rating") is not None:
                bits.append(f"Rating {p['rating']}")
            if p.get("phone"):
                bits.append(p["phone"])
            if bits:
                st.text(" · ".join(bits))
            site = http_url(p.get("website"))
            if site:
                st.link_button("Website", site, key=f"site_{i}")


def render_explorer() -> None:
    st.subheader("Visibility explorer")
    rows, note, date = [], "", ""
    if not DEMO_MODE:
        try:
            r = requests.get(f"{API_URL}/api/coverage", timeout=10)
            r.raise_for_status()
            data = r.json()
            rows = data.get("rows", [])
            note = data.get("method_note", "")
            date = data.get("snapshot_date", "")
        except Exception:
            pass
    if rows:
        st.dataframe(rows, use_container_width=True)  # plain sortable table
        st.caption(f"Snapshot date: {date}")
        st.caption(
            note
            or (
                "One lens (Google Jobs), snapshot date, query-dependent. "
                "Low visibility does not prove low demand."
            )
        )
    else:
        st.text("Visibility snapshot not available yet.")


def main() -> None:
    st.title("Language Opportunity Radar")
    st.caption("Find jobs and language-service providers where your language matters.")

    with st.form("search"):
        c1, c2, c3 = st.columns([2, 3, 1])
        language = c1.selectbox("Language", get_languages())
        location = c2.text_input("City / state", max_chars=80, placeholder="Chennai")
        pin = c3.text_input("PIN (optional)", max_chars=6)
        submitted = st.form_submit_button("Search")

    if submitted:
        loc = location.strip()
        if len(loc) < 2:
            st.warning("Please enter a city (at least 2 characters).")
        elif pin and not (pin.isdigit() and len(pin) == 6):
            st.warning("PIN code must be exactly 6 digits.")
        else:
            with st.spinner("Searching..."):
                payload, msg = run_search(language, loc, pin)
            st.session_state["result"] = {
                "payload": payload,
                "msg": msg,
                "language": language,
                "city": loc,
            }

    res = st.session_state.get("result")
    tab_results, tab_explorer = st.tabs(["Results", "Visibility explorer"])

    with tab_results:
        if not res:
            st.text("Choose a language and city to begin.")
        else:
            payload, meta = res["payload"], res["payload"].get("meta", {})
            if res["msg"]:
                st.info(res["msg"])
            if payload:
                st.caption(
                    f"{SOURCE_BADGE.get(meta.get('source'), 'Unknown source')} · "
                    f"Daily budget remaining: {meta.get('daily_budget_remaining', 'n/a')}"
                )
                if payload.get("notice"):
                    st.warning(payload["notice"])
                vis = meta.get("visibility") or {}
                m1, m2 = st.columns(2)
                m1.metric("Explicit matches", vis.get("explicit", 0))
                m2.metric("Inferred matches", vis.get("inferred", 0))

                listings = payload.get("listings") or []
                st.subheader("Listings")
                if listings:
                    key = st.selectbox("Sort by", ["Relevance", "Posted date", "Location"])
                    for i, item in enumerate(sort_listings(listings, key)):
                        render_listing(item, i)
                else:
                    st.text("No listings found. Coverage here may be low. See providers below.")
                st.subheader("Providers")
                render_providers(payload.get("providers") or [], res["city"])

    with tab_explorer:
        render_explorer()


main()
