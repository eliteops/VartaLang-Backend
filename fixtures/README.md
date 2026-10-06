# SerpApi fixtures

Raw SerpApi JSON responses saved during the Day-1 spike and subsequent runs.

These let tests, QA and the Streamlit UI run **without an API key** and **without
burning credits**. Naming conventions:

- `raw_search_<language>_<city>.json` — raw `google_jobs` responses (Day-1 spike).
- `maps_<city>.json` — raw `google_maps` responses (Day-1 spike).
- `_spike_report.json` — counts, errors and credit usage for the spike run.
- `search_<language>_<city>.json` — **reserved** for curated section-10
  contract-shape samples consumed by the Streamlit skeleton / demo mode
  (not raw upstream responses).
