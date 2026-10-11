"""Backward-compatible re-export: source of truth lives in app.core.scoring."""

from app.core.scoring import *  # noqa: F403
from app.core.scoring import (  # noqa: F401
    EXPLICIT,
    MAY_NEED,
    LanguageKeywords,
    ScoredListing,
    load_keywords,
    score_listing,
    score_listings,
)
