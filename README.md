# VartaLang Language Opportunity Radar

A working, locally-runnable MVP for the **SerpApi India Hackathon 2026** (track: Knowledge & Public Interest).

Pick a **language** and a **city** and get:
1. **Listings** — live Google Jobs results where the language plausibly matters, each with an explainable relevance label and evidence chips.
2. **Providers** — nearby language-service businesses (translation, transcription, localization) from Google Maps.
3. **Visibility** — a dated snapshot of how covered that language–city pair looks, with a methodology note.

> Status: **Step 1 (scaffold) complete.** API core, scoring, Maps module, cache/budget and the Streamlit UI land in the following steps.

---

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python package/project manager) — `uv` installs Python 3.12 for you.
- Docker + Docker Compose — **optional**, only for the local Postgres fallback.

## Setup

```bash
# 1. Provision Python 3.12 and install dependencies into .venv
uv sync

# 2. Create your local env file from the template
cp .env.example .env      # then edit .env and fill in real values
```

`uv sync` creates `.venv`, installs everything from `pyproject.toml` (including the
`dev` dependency group) and writes `uv.lock`.

## Run the API

```bash
uv run uvicorn app.main:app --reload
```

Then open:

- Health: <http://127.0.0.1:8000/api/health> → `{"status":"ok","version":"0.1.0"}`
- Interactive docs: <http://127.0.0.1:8000/docs>

## Test and lint

```bash
uv run ruff check .          # lint
uv run ruff format --check . # formatting check
uv run pytest                # unit tests (no DB / no API key needed)
```

## Database

- **Default (primary): Neon Postgres.** Put the pooled connection string in `.env`
  as `DATABASE_URL`. The engine is tuned for Neon (`pool_pre_ping`, `pool_recycle`,
  prepared statements disabled for the PgBouncer pooler).
- **Optional offline fallback:** a local Postgres via Docker Compose.

```bash
docker compose up -d
# then set DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/vartalang_radar
```

## Configuration

All settings come from environment variables (or `.env`). See `.env.example`:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (Neon pooled, or local). |
| `SERPAPI_KEY` | SerpApi key. Server-side only; never exposed to the frontend. |
| `SERPAPI_DAILY_CAP` | Global daily cap on SerpApi calls. |
| `SERPAPI_TIMEOUT_SECONDS` | Upstream request timeout. |
| `DEMO_MODE` | `1` serves seeded fixtures only — no API key, no upstream calls. |
| `FRONTEND_ORIGINS` | Comma-separated CORS origins for the Streamlit frontend. |
| `ENVIRONMENT` | Free-form environment label. |

## Project layout

```
app/            FastAPI app (main.py, config.py, api/, core/, services/, db/, schemas/)
data/           allowlist, keyword lists, city coordinates, provider filters (owner: Dhawal)
fixtures/       saved SerpApi JSON responses (run without a key)
content/        Markdown page copy (owner: Dhawal)
streamlit_app/  Streamlit UI
tests/          unit tests
docker-compose.yml   optional local Postgres
.env.example         environment template
```

---

## SerpApi usage

*(Filled in as each engine is wired up.)*

| Engine | Feature it powers | Key parameters |
|---|---|---|
| `google_jobs` | Language-relevant job listings | `q`, `location`, `gl=in`, `hl`, `next_page_token` |
| `google_maps` | Nearby language-service providers | `q`, `ll`, `start` |

## License

MIT — see [LICENSE](LICENSE).