# tests/test_scoring.py
from app.scoring import (
    EXPLICIT,
    MAY_NEED,
    LanguageKeywords,
    score_listing,
    score_listings,
)

TAMIL = LanguageKeywords.from_dict("Tamil", {"names": ["தமிழ்"]})
HINDI = LanguageKeywords.from_dict("Hindi", {"names": ["हिंदी", "हिन्दी"]})
MAITHILI = LanguageKeywords.from_dict("Maithili", {"names": ["मैथिली"], "adjacent": ["Hindi"]})


def L(title, location="Chennai, Tamil Nadu", snippet="", age=3):
    return {"title": title, "location": location, "snippet": snippet, "posted_days_ago": age}


def test_name_in_title_with_role_and_location_is_explicit():
    s = score_listing(L("Tamil Translator"), TAMIL, "Chennai")
    assert s.label == EXPLICIT
    assert s.score == 5 + 2 + 1
    assert "Tamil (title)" in s.matched_terms


def test_name_only_in_description_scores_three_and_is_explicit():
    s = score_listing(
        L("Content Writer", location="Pune", snippet="Fluent Tamil required"), TAMIL, "Chennai"
    )
    assert s.label == EXPLICIT
    assert s.score == 3


def test_no_name_but_role_plus_location_is_may_need():
    s = score_listing(L("Voice Process Executive"), TAMIL, "Chennai")
    assert s.label == MAY_NEED
    assert s.score == 3


def test_low_score_is_dropped():
    assert score_listing(L("Accountant"), TAMIL, "Chennai") is None
    # role term alone (wrong city) = 2, below threshold
    assert score_listing(L("Translator", location="Mumbai"), TAMIL, "Chennai") is None


def test_old_listing_is_dropped():
    assert score_listing(L("Tamil Translator", age=45), TAMIL, "Chennai") is None


def test_unknown_age_is_kept():
    assert score_listing(L("Tamil Translator", age=None), TAMIL, "Chennai") is not None


def test_tamil_nadu_is_not_a_language_match():
    s = score_listing(
        L("Sales Executive", snippet="Work with Tamil Nadu dealers"), TAMIL, "Chennai"
    )
    assert s is None


def test_native_script_match():
    s = score_listing(L("हिंदी अनुवादक", location="Delhi"), HINDI, "Delhi")
    assert s.label == EXPLICIT
    assert s.score >= 5


def test_adjacent_language_is_inferred_and_not_explicit():
    s = score_listing(L("Hindi Translator", location="Patna, Bihar"), MAITHILI, "Patna")
    assert s.label == MAY_NEED
    assert "inferred: Hindi" in s.matched_terms


def test_word_boundary():
    kw = LanguageKeywords.from_dict("Hindi", {})
    assert score_listing(L("Hindi-speaking Agent", location="Delhi"), kw, "Delhi") is not None
    assert score_listing(L("Hinduism Researcher", location="Delhi"), kw, "Delhi") is None


def test_sorting_best_score_first():
    rows = [L("Voice Process Executive"), L("Tamil Translator"), L("Accountant")]
    out = score_listings(rows, TAMIL, "Chennai")
    assert [o.listing["title"] for o in out] == ["Tamil Translator", "Voice Process Executive"]
