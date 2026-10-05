# app/scoring.py
"""Rule-based language-relevance scoring (PRD v1.2, section 8 / FR-4).

Pure functions only: no network, no database. Everything is explainable, so
each scored listing carries the evidence (matched_terms) behind its score.

Scoring signals (starting values, tune after the spike):
    language name / native-script name in title        +5
    language name / native-script name in description +3
    language-centric role term in title                +2
    generic "regional language" / "vernacular" mention +1
    listing location matches target city/state         +1
    adjacent-language match (dialect pairs only)       +1  (labelled inferred)

Labels:
    explicit_match  : language name present AND score >= 3
    may_need        : no language name, but score >= 3
    dropped (None)  : everything else, and anything older than 30 days
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

EXPLICIT = "Explicit match"
MAY_NEED = "May need this language"

MIN_SCORE = 3.0
MAX_AGE_DAYS = 30

W_NAME_TITLE = 5
W_NAME_DESC = 3
W_ROLE_TITLE = 2
W_GENERIC = 1
W_LOCATION = 1
W_ADJACENT = 1

# Language-centric role terms (regexes, matched against the lowercased title).
ROLE_PATTERNS: dict[str, str] = {
    "translator": r"\btranslat\w*",
    "interpreter": r"\binterpret(?:er|ers|ing|ation)\b",
    "transcription": r"\btranscri(?:ption|ber|bers|bing|pt)\w*",
    "localization": r"\blocali[sz]ation\b",
    "multilingual support": r"\bmultilingual\b",
    "voice": r"\bvoice\b",
    "linguist": r"\blinguist\w*",
    "annotation": r"\bannotat\w*",
}

GENERIC_PATTERNS: tuple[str, ...] = (
    r"\bregional\s+language",
    r"\bvernacular\b",
    r"\blocal\s+language",
)

# Phrases that contain a language name but are not about the language
# (e.g. the state "Tamil Nadu"). Removed from text before matching.
MASKED_PHRASES: tuple[str, ...] = ("tamil nadu", "tamilnadu")


@dataclass(frozen=True)
class LanguageKeywords:
    """Keyword set for one language, loaded from data/keywords/<language>.json.

    names:    language name(s) incl. native-script spellings.
    adjacent: names of adjacent languages (dialect pairs only, e.g. Hindi
              for Maithili). Empty for standalone languages.
    """

    language: str
    names: tuple[str, ...]
    adjacent: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, language: str, data: dict) -> LanguageKeywords:
        def collect(*keys: str) -> list[str]:
            out: list[str] = []
            for key in keys:
                val = data.get(key)
                if isinstance(val, str):
                    out.append(val)
                elif isinstance(val, (list, tuple)):
                    out.extend(v for v in val if isinstance(v, str))
            return out

        names = collect("names", "name", "native", "native_names", "native_script", "aliases")
        adjacent = collect("adjacent", "adjacent_languages")
        names = [language, *names]
        return cls(
            language=language,
            names=tuple(dict.fromkeys(n.strip() for n in names if n.strip())),
            adjacent=tuple(dict.fromkeys(a.strip() for a in adjacent if a.strip())),
        )


def load_keywords(language: str, data_dir: str | Path = "data/keywords") -> LanguageKeywords:
    path = Path(data_dir) / f"{language.strip().lower()}.json"
    with path.open(encoding="utf-8") as fh:
        return LanguageKeywords.from_dict(language, json.load(fh))


@dataclass
class ScoredListing:
    listing: dict
    score: float
    label: str
    matched_terms: list[str] = field(default_factory=list)


def _norm(text: str | None) -> str:
    text = (text or "").casefold()
    for phrase in MASKED_PHRASES:
        text = text.replace(phrase, " ")
    return text


def _contains(text: str, term: str) -> bool:
    term = term.strip().casefold()
    if not term:
        return False
    if term.isascii():
        # Word-boundary match for Latin text.
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    # Indic scripts: combining marks break \b, so use a plain substring match.
    return term in text


def _first_hit(text: str, terms: tuple[str, ...]) -> str | None:
    for term in terms:
        if _contains(text, term):
            return term
    return None


def _location_match(listing_location: str | None, target_location: str) -> bool:
    loc = (listing_location or "").casefold()
    if not loc:
        return False
    tokens = [t.strip().casefold() for t in re.split(r"[,\-]", target_location)]
    return any(len(t) >= 3 and t in loc for t in tokens)


def score_listing(
    listing: dict,
    kw: LanguageKeywords,
    target_location: str,
    max_age_days: int = MAX_AGE_DAYS,
) -> ScoredListing | None:
    """Score one parsed listing. Returns None if it should be dropped.

    Expected listing keys: title, location, snippet (or description),
    posted_days_ago (None when unknown).
    """
    age = listing.get("posted_days_ago")
    if age is not None and age > max_age_days:
        return None

    title = _norm(listing.get("title"))
    desc = _norm(listing.get("snippet") or listing.get("description"))

    score = 0.0
    chips: list[str] = []

    # Language name / native-script name.
    name_in_title = _first_hit(title, kw.names)
    name_in_desc = _first_hit(desc, kw.names)
    if name_in_title:
        score += W_NAME_TITLE
        chips.append(f"{name_in_title} (title)")
    if name_in_desc:
        score += W_NAME_DESC
        chips.append(f"{name_in_desc} (description)")
    has_name = bool(name_in_title or name_in_desc)

    # Language-centric role term in the title (counted once).
    for role, pattern in ROLE_PATTERNS.items():
        if re.search(pattern, title):
            score += W_ROLE_TITLE
            chips.append(f"role: {role}")
            break

    # Generic regional-language mention (counted once).
    for pattern in GENERIC_PATTERNS:
        if re.search(pattern, f"{title} {desc}"):
            score += W_GENERIC
            chips.append("regional language mention")
            break

    # Location.
    if _location_match(listing.get("location"), target_location):
        score += W_LOCATION
        chips.append("location match")

    # Adjacent language (dialect pairs only), labelled as inferred.
    if kw.adjacent:
        adj = _first_hit(title, kw.adjacent) or _first_hit(desc, kw.adjacent)
        if adj:
            score += W_ADJACENT
            chips.append(f"inferred: {adj}")

    if score < MIN_SCORE:
        return None

    label = EXPLICIT if has_name else MAY_NEED
    return ScoredListing(listing=listing, score=score, label=label, matched_terms=chips)


def score_listings(
    listings: list[dict],
    kw: LanguageKeywords,
    target_location: str,
) -> list[ScoredListing]:
    """Score, drop and sort (best score first, then most recent)."""
    scored = [s for item in listings if (s := score_listing(item, kw, target_location))]
    scored.sort(
        key=lambda s: (
            -s.score,
            s.listing.get("posted_days_ago")
            if s.listing.get("posted_days_ago") is not None
            else 999,
        )
    )
    return scored
