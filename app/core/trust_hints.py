"""Soft trust-hint detector (PRD v1.2, FR-14).

Pure functions over the Dhawal-owned `data/trust_hint_patterns.json`:
patterns are Python `re` syntax, matched with IGNORECASE against the
NFC-normalized listing text (title + snippet/description). Each hint fires
at most once per listing. Wording is always soft ("Worth double-checking:")
-- never "scam" or "verified". Bad patterns fail safe (skipped, never crash).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PATTERNS_FILE = DATA_DIR / "trust_hint_patterns.json"


@dataclass(frozen=True)
class TrustHint:
    id: str
    message: str
    patterns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledHint:
    id: str
    message: str
    regexes: tuple[re.Pattern[str], ...] = field(default_factory=tuple)


def _flags(name: str | None) -> int:
    if (name or "").strip().upper() == "IGNORECASE":
        return re.IGNORECASE
    return 0


def _compile(pattern: str, flags: int) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern, flags)
    except re.error:
        return None


def load_hints(path: str | Path = PATTERNS_FILE) -> tuple[CompiledHint, ...]:
    with Path(path).open(encoding="utf-8") as fh:
        doc = json.load(fh)
    flags = _flags(doc.get("flags"))
    compiled: list[CompiledHint] = []
    for hint in doc.get("hints", []) or []:
        hint_id = str(hint.get("id", "")).strip()
        message = str(hint.get("message", "")).strip()
        if not hint_id or not message:
            continue
        regexes = [
            rx
            for p in (hint.get("patterns", []) or [])
            if isinstance(p, str) and (rx := _compile(p, flags)) is not None
        ]
        if regexes:
            compiled.append(CompiledHint(id=hint_id, message=message, regexes=tuple(regexes)))
    return tuple(compiled)


@lru_cache(maxsize=1)
def get_hints() -> tuple[CompiledHint, ...]:
    try:
        return load_hints()
    except (OSError, ValueError):
        return ()


def _listing_text(listing: dict) -> str:
    parts = [listing.get("title"), listing.get("snippet"), listing.get("description")]
    text = " ".join(str(p) for p in parts if p)
    return unicodedata.normalize("NFC", text)


def detect_trust_hints(listing: dict, hints: tuple[CompiledHint, ...] | None = None) -> list[str]:
    if hints is None:
        hints = get_hints()
    text = _listing_text(listing)
    if not text:
        return []
    return [h.message for h in hints if any(rx.search(text) for rx in h.regexes)]
