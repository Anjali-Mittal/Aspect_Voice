# FeedbackForge — Project Handover

## What this is

FeedbackForge turns scattered public feedback about a product into a
priority-ranked list of real issues, usable directly by R&D. Built as a PwC
internship POC for Hero MotoCorp, currently configured for the Hero Xtreme
125R.

It scans Reddit, YouTube comments, and review sites (BikeDekho, ZigWheels,
BikeWale), discovers on its own what features/aspects customers actually
talk about — no predefined feature list — then extracts sentiment and
severity per aspect, clusters negative mentions into distinct real issues,
and ranks them by volume + severity + recency. Every insight is traceable
back to its original source review.

100% free-tier stack. No credit card required anywhere, for any service.

## Stack

- **Backend**: FastAPI + SQLAlchemy
- **DB**: NeonDB (serverless Postgres) — no local DB, no Docker
- **LLM**: Groq (primary) + Google AI Studio / Gemini (fallback) — both
  free tier, no card. Each provider tries its own two-model chain before
  falling to the other; a rate limit on one provider falls through to the
  other immediately rather than waiting
- **Ingestion**: Reddit (PRAW), YouTube Data API v3, review-site scraping
  (JSON-LD schema.org parsing for BikeDekho/BikeWale, CSS selectors for
  ZigWheels — no paid review API, no Google Places)
- **Frontend**: React + TypeScript + Tailwind v4, built with Vite
- **Hosting target**: Render (free tier)

## Pipeline — 6 stages

Each stage is its own module under `app/pipeline/`, triggered individually
or all at once via `POST /pipeline/run-all`. Idempotent — each stage skips
rows it's already processed, except clustering, which always rebuilds
fresh from current data.

1. **Ingest** (`ingest.py`) — pulls from all enabled sources, dedups by
   source-native ID, writes `RawFeedback`
2. **Relevance filter** (`relevance_filter.py`) — LLM drops off-topic,
   spam, or content-free items; marks `RawFeedback.is_relevant`
3. **Cleaning** (`cleaning.py`) — normalizes text, fuzzy-dedups
   near-identical reviews (rapidfuzz, threshold 92) that slip past
   exact-ID dedup; writes `CleanFeedback`. Every stage after this reads
   from `CleanFeedback`, never `RawFeedback` directly
4. **Ontology discovery** (`ontology_discovery.py`) — LLM derives the
   actual feature list from a sample of real cleaned feedback; writes
   `FeatureOntology`. No feature name is ever hardcoded in Python —
   verified by grep during development
5. **Aspect extraction** (`aspect_extraction.py`) — LLM maps each clean
   item to feature(s) + sentiment + severity + a verbatim evidence
   snippet, using only features from the discovered ontology; writes
   `AspectMention`
6. **Clustering + scoring** (`clustering_scoring.py`) — groups negative
   mentions per feature into distinct issues via LLM, computes:
   - `priority_score` = 0.4·volume + 0.4·avg_severity + 0.2·recency
   - `trend` (increasing/stable/decreasing/insufficient_data) — real
     comparison of mention counts across two time-bucket halves of the
     trend window, not invented; needs ≥6 members or returns
     `insufficient_data`
   - `confidence` — evidence-volume proxy (mention_count/15, capped at
     1.0), explicitly not a statistical confidence interval
   - `primary_context` + `recommended_investigation` — short LLM-derived
     usage context and a one-sentence investigation suggestion, framed as
     decision support, never as proof of a defect
   Writes `IssueCluster` plus `IssueClusterMember` (full evidence chain —
   every contributing mention linked to its cluster, not just a top-5
   sample)

## Automatic runs

The pipeline re-runs on its own, default every 30 days
(`config.yaml -> schedule.interval_days`). Render's free tier has no free
cron of its own (its cron service bills per-minute, needs a card), so this
uses a free external pinger instead:

- `POST /pipeline/scheduled-trigger` — gated by a shared secret
  (`SCHEDULER_SECRET` env var, checked against an `X-Scheduler-Secret`
  header), only actually executes if `interval_days` has elapsed since the
  last scheduled run (`app/pipeline/scheduler.py -> is_due()`)
- `GET /pipeline/schedule-status` — real run history, not a claim
- Setup: a free cron-job.org account pings the trigger endpoint daily; the
  interval math lives server-side so the pinger's schedule doesn't need to
  be exact (see DEPLOYMENT.md section 6)

## Data model (`app/models/db.py`)

```
RawFeedback         — one scraped item per source, deduped by source_id
CleanFeedback        — normalized + fuzzy-deduped, FK to RawFeedback
FeatureOntology       — LLM-discovered features, per product
AspectMention          — feature + sentiment + severity per CleanFeedback item
IssueCluster            — grouped negative mentions = one real issue
IssueClusterMember       — join table: full evidence chain, mention -> cluster
PipelineRunLog            — every scheduled pipeline execution, for schedule-status
```

## API (`app/api/`)

Split into two router modules, both included from `main.py`:

**`pipeline_routes.py`** — `/pipeline/*`: ingest, relevance-filter,
cleaning, ontology-discovery, aspect-extraction, cluster-score, run-all,
scheduled-trigger, schedule-status

**`insights_routes.py`** — read endpoints, all computed live from the DB,
never a placeholder or invented number:
- `GET /vehicles` — distinct product names actually ingested (not a
  hardcoded catalogue)
- `GET /features?vehicle=X` — discovered feature list
- `GET /features/{name}/summary?vehicle=X` — mentions, sentiment %,
  severity %
- `GET /issues?vehicle=X` — priority-ranked issues; filterable by
  `feature`, `trend`, `severity`, `min_priority`
- `GET /issues/{id}` — full cluster detail incl. monthly trend bars and
  source-group count, for the Evidence Explorer header
- `GET /issues/{id}/evidence` — full evidence list, each item split into
  `observed` (raw text/author/source/url) vs `ai_interpretation`
  (snippet/sentiment/severity)
- `GET /overview?vehicle=X` — everything the Overview page needs in one
  call: KPIs, sentiment trend by month, top strengths, top pain points,
  emerging issues
- `GET /stats?vehicle=X` — pipeline funnel counts

## Frontend (`frontend/`)

Two pages built, per `DASHBOARD.md` (the UX spec — kept in the repo as
source of truth):

**Product Overview** (`pages/OverviewPage.tsx`) — KPI cards, sentiment
trend line chart, top strengths, top pain points, emerging issues.

**Product Insights** (`pages/ProductInsightsPage.tsx`) — discovered-feature
sidebar with click-through summary panel; ranked issue table with All /
High Priority / Emerging filter tabs plus feature/severity filtering.
Clicking a row opens:

**Evidence Explorer** (`pages/EvidenceExplorerPage.tsx`) — slide-in drawer:
priority/trend/confidence header, monthly trend bar chart, primary context
+ recommendation (visually flagged as decision support, not diagnosis),
full evidence list with Observed vs. AI Interpretation split and links back
to the original source.

API contract is centralized in `frontend/src/api/client.ts` — every backend
field the UI depends on is typed there; nothing else in the frontend talks
to the backend directly.

Empty states are handled everywhere per `DASHBOARD.md` section 14 — no
fake zeroes, no invented insights when data isn't there yet.

## Config vs. code

Nothing that changes between products, sources, or environments lives in
Python:

- `config/config.yaml` — target product, source lists (subreddits, search
  terms, review-site CSS selectors / JSON-LD mode), pipeline tuning (batch
  sizes, thresholds, trend window, high-priority cutoff), schedule interval
- `.env` (backend) / `frontend/.env` — DB connection, all API keys,
  host/port/CORS, scheduler secret, frontend API base URL

Swapping to a different vehicle/product is a config edit, not a code
change — and multi-vehicle already works at the DB level (every table is
keyed by `product_name`); `/vehicles` surfaces whatever's actually been
ingested.

## What's not built yet (from DASHBOARD.md scope)

- Date-range filtering on Overview/Insights (backend supports month-level
  data; no date-range query param yet)
- Use-case/customer segment filtering
- Competitive comparison mode (explicitly Phase 2 per spec section 10)
- Historical ontology evolution tracking
- Automated recommendation tracking (has recommendations, no tracking of
  whether they were acted on)

## Known limitations, stated plainly

- ZigWheels review scraping only gets the ~13 reviews rendered
  server-side — no pagination URL param was found on the page; the rest
  likely loads via JS "load more" which would need its own endpoint
  identified
- BikeWale's CSS classes are build-hashed (regenerate every deploy) and
  unusable for selector-based scraping; its JSON-LD only carries one
  sample review (an SEO rich snippet), so it's a low-volume source by
  design, not a bug
- No automated visual/screenshot testing was possible during development
  (sandboxed environment couldn't install a browser) — functionality was
  verified via real seeded data through the actual API and a clean
  TypeScript build, but a manual visual pass is still worth doing

## Repo layout

```
app/
  config.py                 .env + config.yaml loader (resolves ${ENV_VAR}
                             and ${target.x} references)
  models/db.py                SQLAlchemy models (Postgres via NeonDB)
  llm/client.py                 Groq caller, model-fallback chain
  ingestion/
    reddit_source.py
    youtube_source.py
    review_site_source.py         JSON-LD + CSS scraping
  pipeline/                         6 stages, see above
  api/
    pipeline_routes.py
    insights_routes.py
  main.py                             FastAPI app setup + router registration
run.py                                  entrypoint, host/port from .env
render.yaml                               Render blueprint (one-click deploy)
config/config.yaml                          all tunables
.env.example                                  backend env template
frontend/
  src/api/client.ts                             typed API contract
  src/components/                                 KpiCard, EmptyState, TrendBadge, AppShell
  src/pages/                                        OverviewPage, ProductInsightsPage, EvidenceExplorerPage
  .env.example                                        frontend env template
README.md                                             what the system does
DEPLOYMENT.md                                           step-by-step local + Render deploy
DASHBOARD.md                                              UX spec, source of truth for frontend work
```

## Immediate next steps

1. Manual visual QA pass on both frontend pages (Overview, Product
   Insights + Evidence Explorer) against real or seeded data
2. Fill in `.env` with real keys and run `POST /pipeline/run-all` against
   NeonDB to get first live results
3. Deploy to Render per DEPLOYMENT.md, set up the cron-job.org monthly
   trigger
4. Decide whether to build the remaining DASHBOARD.md scope (date-range
   filters, competitive comparison) or treat current state as POC-complete
