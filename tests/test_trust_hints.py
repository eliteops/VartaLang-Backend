"""Tests for the soft trust-hint detector (PRD FR-14)."""

from app.core.trust_hints import (
    CompiledHint,
    detect_trust_hints,
    get_hints,
    load_hints,
)

WHATSAPP_HINDI = (
    "\u0935\u094d\u0939\u093e\u091f\u094d\u0938\u0910\u092a "
    "\u092a\u0930 \u092d\u0947\u091c\u0947\u0902"
)
REG_FEE_HINDI = (
    "\u0930\u091c\u093f\u0938\u094d\u091f\u094d\u0930\u0947\u0936\u0928 "
    "\u092b\u0940\u0938 \u0926\u0947\u0902"
)
BAD_HINTS_JSON = (
    '{"flags": "IGNORECASE", "hints": [{"id": "x", '
    '"message": "Worth double-checking: x", "patterns": ["(["]}]}'
)


def L(title="", snippet=""):
    return {"title": title, "snippet": snippet}


def test_real_patterns_load_two_hints() -> None:
    hints = get_hints()
    assert [h.id for h in hints] == ["personal_messaging", "application_fee"]
    assert all(h.message.startswith("Worth double-checking:") for h in hints)
    assert all("scam" not in h.message and "verified" not in h.message for h in hints)


def test_whatsapp_and_telegram_fire() -> None:
    assert detect_trust_hints(L(snippet="Apply via WhatsApp 98xxx")) != []
    assert detect_trust_hints(L(snippet="Join our telegram channel")) != []
    assert detect_trust_hints(L(snippet="wa.me/9198xxx")) != []
    assert detect_trust_hints(L(snippet="DM us your resume")) != []


def test_hindi_variants_fire() -> None:
    assert detect_trust_hints(L(snippet=WHATSAPP_HINDI)) != []
    assert detect_trust_hints(L(snippet=REG_FEE_HINDI)) != []


def test_fee_patterns_fire() -> None:
    assert detect_trust_hints(L(snippet="Refundable security deposit Rs 2000")) != []
    assert detect_trust_hints(L(snippet="Pay Rs 500 registration fee")) != []
    assert detect_trust_hints(L(snippet="Training fee applicable")) != []


def test_clean_listing_has_no_hints() -> None:
    assert detect_trust_hints(L("Tamil Translator", "Native fluency required")) == []
    assert detect_trust_hints({}) == []


def test_each_hint_fires_once() -> None:
    out = detect_trust_hints(L(snippet="WhatsApp us, or Telegram us, wa.me/x"))
    assert len(out) == 1


def test_bad_pattern_fails_safe(tmp_path) -> None:
    bad = tmp_path / "hints.json"
    bad.write_text(BAD_HINTS_JSON, encoding="utf-8")
    assert load_hints(bad) == ()
    hint = CompiledHint(id="x", message="Worth double-checking: x", regexes=())
    assert detect_trust_hints(L(snippet="anything"), hints=(hint,)) == []
