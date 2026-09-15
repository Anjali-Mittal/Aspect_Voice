# Customer Voice Intelligence

Turns scattered public feedback about a product into a priority-ranked list
of real issues — usable directly by R&D.

Give it a product (currently: Hero Xtreme 125R). It scans Reddit, YouTube
comments, and review sites (BikeDekho, ZigWheels, BikeWale), figures out on
its own what features/aspects people actually talk about — no predefined
list — then extracts sentiment and severity per aspect, groups negative
mentions into distinct real issues, and ranks them by volume + severity +
recency.

## Stack

- **Backend**: FastAPI + SQLAlchemy
- **DB**: NeonDB (serverless Postgres) — no local DB, no Docker
- **LLM**: Groq (primary), Google AI Studio / Gemini (fallback) — both free tier, no credit card
- **Ingestion**: Reddit (PRAW), YouTube Data API v3, review-site scraping
  (JSON-LD schema.org parsing + CSS selectors — no paid review API)
- **Hosting**: Render (free tier)

Nothing in this stack requires a credit card at any point.

## How it works — 6-stage pipeline

1. **Ingest** — pull raw feedback from every enabled source, dedup by
   source-native ID
2. **Relevance filter** — LLM drops off-topic/spam/content-free items
3. **Cleaning** — normalize text, fuzzy-dedup near-identical reviews
   (rapidfuzz) that slip past exact-ID dedup — writes `CleanFeedback`,
   which every later stage reads from, never `RawFeedback` directly
4. **Ontology discovery** — LLM derives the actual feature list from real
   text (no hardcoded feature names anywhere)
5. **Aspect extraction** — LLM maps each item to feature(s) + sentiment +
   severity, with a verbatim evidence snippet
6. **Clustering + scoring** — groups negative mentions per feature into
   distinct issues, scores by `0.4·volume + 0.4·severity + 0.2·recency`,
   and records the full evidence chain (`IssueClusterMember`) linking every
   contributing mention back to its source review — not just a top-5 sample

Each stage is a separate module under `app/pipeline/` — trigger individually
via API, or all at once via `/pipeline/run-all`. Re-running is idempotent:
each stage skips rows it's already processed, except clustering, which
always rebuilds fresh.

## Automatic runs

The full pipeline re-runs on its own — default every 30 days
(`config.yaml -> schedule.interval_days`) — via `POST
/pipeline/scheduled-trigger`, gated by a shared secret so it's not a public
endpoint. No paid scheduler, no card: see DEPLOYMENT.md section 6 for the
free cron-job.org setup. `GET /pipeline/schedule-status` shows real run
history, not just a claim that it's scheduled.

## Config vs. code

Everything that changes between products, sources, or environments lives in
`config/config.yaml` or `.env` — never in Python:

- `config/config.yaml` — target product, source lists (subreddits, search
  terms, review-site selectors), pipeline tuning (batch sizes, thresholds)
- `.env` — DB connection, API keys, host/port/CORS (see `.env.example`)

Swapping to a different vehicle/product is a config edit, not a code change.

## Project layout

```
app/
  config.py               config + .env loader (resolves both ${target.x}
                           and ${ENV_VAR} references)
  models/db.py             SQLAlchemy models (Postgres via NeonDB)
  llm/client.py             Groq caller, model-fallback chain
  ingestion/
    reddit_source.py
    youtube_source.py
    review_site_source.py   JSON-LD + CSS scraping, no paid API
  pipeline/
    ingest.py                stage 1 orchestrator
    relevance_filter.py       stage 2
    cleaning.py                stage 3 — normalize + fuzzy dedup (rapidfuzz)
    ontology_discovery.py     stage 4
    aspect_extraction.py      stage 5
    clustering_scoring.py     stage 6 — also writes full evidence chain
  main.py                  FastAPI routes only, no business logic
run.py                     entrypoint — host/port from .env, same command
                            locally and on Render
render.yaml                Render blueprint (one-click deploy config)
config/config.yaml         all tunables
.env.example                template for required env vars
```

## Frontend

`frontend/` — React + TypeScript + Tailwind (v4), built with Vite.

Two pages built:
- **Product Overview** (DASHBOARD.md section 3) — KPI cards, sentiment trend
  chart, top strengths, top pain points, emerging issues
- **Product Insights** (sections 4–8) — discovered-feature sidebar with
  click-through summary, filterable ranked-issue table (All / High Priority
  / Emerging tabs, plus feature/severity filters), clicking a row opens the
  **Evidence Explorer** as a drawer (section 9) — priority/trend/confidence
  header, monthly trend bars, primary context + recommendation (clearly
  marked as decision support, not a diagnosis), and the full Observed vs. AI
  Interpretation evidence list with source links

All live-fetched, vehicle-selectable, honest empty states throughout
(section 14 — never a fake zero).

```bash
cd frontend
npm install
cp .env.example .env      # set VITE_API_BASE_URL if backend isn't on localhost:8000
npm run dev
```

API contract lives in one place: `frontend/src/api/client.ts` — every
backend field the UI depends on is typed there.

For setup and deployment steps, see **DEPLOYMENT.md**.