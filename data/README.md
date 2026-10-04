# Data files (allowlist, per-language keyword lists, city coordinates, provider filters, trust hints)

Content owned by Dhawal (product & security lead); code that loads these files is owned by Harshit.

These files hold **terms and lists only**. Scoring weights, thresholds and logic live in code (PRD section 8), not here. That way Dhawal can tune vocabulary without touching code, and Harshit can tune scoring without touching vocabulary.

## Layout

```
data/
├── README.md
├── languages.json
├── cities.json
├── provider_filters.json
├── trust_hint_patterns.json
└── keywords/
    ├── _common.json
    ├── hindi.json
    ├── tamil.json
    ├── bengali.json
    ├── maithili.json
    ├── bhojpuri.json
    ├── telugu.json
    ├── marathi.json
    └── gujarati.json
```

## Conventions (please read first)

- **Encoding:** UTF-8 without BOM. Open files with `encoding="utf-8"`. Many values are Devanagari, Tamil, Bengali, Telugu and Gujarati script.
- **Ids:** lowercase ASCII (`hindi`, `delhi-ncr`). The same id is used across files: `languages.json` ids = `keywords/<id>.json` filenames = the `language` field inside each keywords file.
- **`_common.json`:** any file in `keywords/` that starts with an underscore is **not a language**. The loader must skip it when listing languages.
- **`version`:** every file has `"version": 1`. Bump it if the structure changes, and say so in the PR.
- **Allowlist is the source of truth.** The API must only accept a `language` that exists in `languages.json` (FR-1). Anything else returns a generic 422.

## `languages.json`

Supported-language allowlist, demo pairs and snapshot grid.

| Field | Meaning |
|---|---|
| `languages[].id` | Stable id, used everywhere |
| `languages[].name` | English display name |
| `languages[].native_name` | Name in its own script, for the UI |
| `languages[].script` | Script name (informational) |
| `languages[].is_dialect` | `true` for Maithili and Bhojpuri |
| `languages[].adjacent_languages` | Ids of related languages, used only for the "+1 inferred" rule |
| `demo_pairs[]` | The 5 rehearsed language-city pairs for the demo and fixtures |
| `snapshot.languages` / `snapshot.cities` | The 8 × 5 grid for the visibility snapshot (FR-13) |

Current languages: Hindi, Tamil, Bengali, Maithili, Bhojpuri, Telugu, Marathi, Gujarati.
Demo pairs: Hindi/Delhi NCR, Tamil/Chennai, Bengali/Kolkata, Maithili/Patna, Bhojpuri/Lucknow.

## `keywords/<language>.json`

Per-language vocabulary for the scorer.

| Field | Meaning |
|---|---|
| `language` | Id, same as the filename |
| `name_terms.english` | English spellings of the language name (e.g. Bengali, Bangla) |
| `name_terms.native_script` | The name in native script, including common spelling variants (e.g. हिन्दी and हिंदी) |
| `native_role_terms` | Role words in that script (translator, translation, interpreter) |
| `adjacent_note` | Reminder only; the adjacency data itself is in `languages.json` |

## `keywords/_common.json`

Shared English terms so they are not duplicated in 8 files.

| Field | Meaning |
|---|---|
| `role_terms` | English role words: translator, interpreter, transcription, localization, etc. |
| `generic_terms` | Weak signals: "regional language", "vernacular", "bilingual", etc. |

## How this maps to the scoring table (PRD section 8)

| PRD signal | Points | Terms come from |
|---|---|---|
| Language name or native-script name in title | +5 | `name_terms.english` + `name_terms.native_script` |
| Language name or native-script name in description | +3 | same |
| Language-centric role term in title | +2 | `_common.role_terms` + `native_role_terms` |
| Generic "regional language" / "vernacular" mention | +1 | `_common.generic_terms` |
| Location matches target city/state | +1 | `cities.json` (`display_name`, `state`, `aliases`) |
| Adjacent-language match (dialect pairs only) | +1, labeled inferred | `adjacent_languages` in `languages.json`, then that language's `name_terms` |

### Matching notes for the loader

- **English terms:** case-insensitive, whole-word match.
- **Native-script terms:** plain substring match. `\b` word boundaries are unreliable for Indic scripts.
- **Normalize to Unicode NFC** on both the listing text and the term lists before matching, so visually identical strings compare equal.
- **Maithili and Bhojpuri** share Devanagari with Hindi. Their *name* terms are distinct (मैथिली, भोजपुरी), but their role terms (अनुवादक, अनुवाद) are the same as Hindi's. A listing that only has those role terms and no language name should not become an Explicit match for Maithili.

## `cities.json`

Static coordinates for the 5 demo cities, so Maps searches need no geocoding.

| Field | Meaning |
|---|---|
| `id` | e.g. `delhi-ncr`, `chennai`, `kolkata`, `patna`, `lucknow` |
| `display_name`, `state` | For the UI and for the location-match signal |
| `lat`, `lng` | Decimal degrees |
| `serpapi_ll` | Ready-made `ll` value for `google_maps`, format `@lat,lng,zoom` |
| `aliases` | Other names a user might type or a listing might use (e.g. Noida, Gurugram for Delhi NCR; Madras for Chennai) |

Use `aliases` to resolve free-text location input (FR-1) to a city, and for the +1 location-match signal.

## `provider_filters.json`

Controls the Google Maps providers module (FR-12).

| Field | Meaning |
|---|---|
| `max_providers` | Cap on providers shown (8) |
| `query_templates` | Maps queries to run; placeholders `{language}` and `{city}` |
| `optional_query_templates` | Extra query, only if credits and time allow |
| `include_categories` / `exclude_categories` | Maps category names to keep or drop |
| `include_name_keywords` / `exclude_name_keywords` | Words to match in the business name |
| `rule` | The filter logic in words (below) |

Filter logic: keep a place if its category is in `include_categories` **or** its name matches `include_name_keywords`. Drop it if its category is in `exclude_categories` **and** its name matches nothing in `include_name_keywords`. Always drop names matching `exclude_name_keywords`.

Language schools and coaching centres are excluded on purpose: they teach, they do not provide translation services. This is a product decision and can be revisited.

## `trust_hint_patterns.json`

Soft flags on listings (FR-14).

| Field | Meaning |
|---|---|
| `flags` | Regex flags to apply (`IGNORECASE`) |
| `hints[].id` | `personal_messaging` or `application_fee` |
| `hints[].message` | Text shown to the user. Always starts with "Worth double-checking:" |
| `hints[].patterns` | List of regexes (Python `re` syntax); a hint fires if any one matches the listing text |

Wording rule: never say "scam", "fake" or "verified". These are soft hints only. A legitimate employer may mention WhatsApp, so a match is a prompt to double-check, not a verdict. Hindi-script variants are included for WhatsApp, Telegram and registration fee.

## Needs verification in the backend spike (Harshit)

These values are best guesses until real SerpApi responses are seen:

1. **`serpapi_ll` format and zoom level** in `cities.json` (spike task 4).
2. **Maps category strings** in `provider_filters.json` (e.g. "Translation service") must match the exact strings returned by `google_maps`.
3. **`hl` codes** are intentionally *not* in these files. Spike task 2 decides which codes work, especially for Maithili and Bhojpuri. Add a field to `languages.json` afterwards if needed.
4. **Query templates** may need changing once the spike shows how the Maps query behaves.

## Changing these files

- Open a short PR; the other person reviews.
- If you add or rename a field, bump `version` and mention it in the PR so the loader and tests are updated together.
- Adding a language: add it to `languages.json`, create `keywords/<id>.json`, and add it to `snapshot.languages` if it should appear in the visibility table.
- The hand-labeled evaluation set (FR-17) doubles as golden test cases for the scorer. If a keyword change moves a golden case, update the case deliberately, not silently.