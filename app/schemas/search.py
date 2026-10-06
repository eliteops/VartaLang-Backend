"""Pydantic request/response models for the public API (PRD v1.2, section 10).

Contract:
- POST /api/search body: `language`, `location`, optional `pin_code` (FR-1).
- Response: `meta`, `listings[]`, `providers[]`, `notice`.
- Errors: generic `{"error": {"code", "message"}}` only (FR-11).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

LOCATION_RE = re.compile(r"^[A-Za-z0-9 ,\-]+$")
PIN_RE = re.compile(r"^\d{6}$")

SourceStatus = Literal["cache", "live", "fallback"]


class SearchRequest(BaseModel):
    """Search input (FR-1). Language allowlist itself is checked in the route."""

    language: str = Field(..., min_length=1, max_length=40)
    location: str = Field(..., min_length=2, max_length=80)
    pin_code: str | None = Field(default=None, max_length=6)

    @field_validator("language")
    @classmethod
    def language_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("language must not be blank")
        return v

    @field_validator("location")
    @classmethod
    def location_chars(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 80):
            raise ValueError("location must be 2 to 80 characters")
        if not LOCATION_RE.match(v):
            raise ValueError(
                "location may only contain letters, digits, spaces, commas and hyphens"
            )
        return v

    @field_validator("pin_code")
    @classmethod
    def pin_format(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not PIN_RE.match(v):
            raise ValueError("pin_code must be exactly 6 digits")
        return v


class ListingItem(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    salary_text: str | None = None
    posted_days_ago: int | None = None
    snippet: str | None = None
    apply_link: str
    source_name: str | None = None
    relevance_label: str
    relevance_score: float
    matched_terms: list[str] = Field(default_factory=list)
    trust_hints: list[str] = Field(default_factory=list)


class ProviderItem(BaseModel):
    name: str
    category: str | None = None
    address: str | None = None
    rating: float | None = None
    website: str | None = None
    phone: str | None = None


class VisibilityCounts(BaseModel):
    explicit: int = 0
    inferred: int = 0


class SearchMeta(BaseModel):
    source: SourceStatus
    fetched_at: str
    daily_budget_remaining: int
    visibility: VisibilityCounts = Field(default_factory=VisibilityCounts)


class SearchResponse(BaseModel):
    meta: SearchMeta
    listings: list[ListingItem] = Field(default_factory=list)
    providers: list[ProviderItem] = Field(default_factory=list)
    notice: str


class LanguageItem(BaseModel):
    id: str
    name: str
    native_name: str


class LanguagesResponse(BaseModel):
    version: int
    languages: list[LanguageItem]


class CoverageRow(BaseModel):
    language: str
    city: str
    explicit_count: int = 0
    inferred_count: int = 0


class CoverageResponse(BaseModel):
    snapshot_date: str
    method_note: str
    rows: list[CoverageRow]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
