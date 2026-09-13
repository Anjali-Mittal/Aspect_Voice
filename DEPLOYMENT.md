# Deployment

Two paths below: local development, and Render (free tier) production
deploy. Same codebase, same entrypoint (`python run.py`) — only `.env`
differs.

---

## 1. Get your free accounts + keys (do this once, either path)

| Service | URL | Notes |
|---|---|---|
| NeonDB | https://neon.tech | Free Postgres, no card. Create a project, copy the connection string. |
| Groq | https://console.groq.com/keys | Free LLM API, no card. |
| Reddit | https://www.reddit.com/prefs/apps | Click "create app", type = "script". No card. |
| YouTube Data API v3 | https://console.cloud.google.com | Enable "YouTube Data API v3" under APIs & Services, create an API key under Credentials. Free daily quota, no card needed at this scale. |
| Render | https://render.com | Free web service tier, no card required for free tier. |
| cron-job.org | https://cron-job.org | Free external scheduler — triggers the monthly pipeline run (see section 6). No card. |

Keep the NeonDB connection string and all keys handy for step 2/4.

---

## 2. Local development

```bash
git clone <your-repo-url>
cd aspectvoice

python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt

cp .env.example .env
```

Edit `.env`:
- Paste your NeonDB `DATABASE_URL` (this is your only database — no local
  Postgres, no SQLite, no Docker needed)
- Paste `GROQ_API_KEY`, Reddit creds, `YOUTUBE_API_KEY`
- Leave `HOST`/`PORT` as-is unless `8000` clashes with something else on
  your machine — if so, change `PORT` only, nothing else needs to match it

Edit `config/config.yaml` if you want a different product/vehicle, different
subreddits, search terms, etc.

Run it:

```bash
python run.py
uvicorn app.main:app --reload
```

Server starts at `http://localhost:8000` (or whatever `PORT` you set).
Interactive API docs: `http://localhost:8000/docs`.

Run the pipeline:

```bash
curl -X POST http://localhost:8000/pipeline/run-all
```

Or trigger stages one at a time — see README.md for the 6-stage breakdown.
Then:

```bash
curl http://localhost:8000/issues              # priority-ranked results
curl http://localhost:8000/issues/1/evidence    # full evidence chain for one issue
curl http://localhost:8000/stats                # pipeline funnel counts
```

---

## 3. Push to a git repo

Render deploys from a git repo (GitHub/GitLab/Bitbucket). If you haven't
already:

```bash
git init
git add .
git commit -m "AspectVoice"
git remote add origin <your-repo-url>
git push -u origin main
```

`.env` is never committed (see `.gitignore`) — Render gets secrets via its
own dashboard, step 4 below.

---

## 4. Deploy to Render

**Option A — Blueprint (recommended, uses `render.yaml`):**

1. Render dashboard → New → Blueprint
2. Connect your repo → Render reads `render.yaml` automatically
3. It creates one free web service, prompts you for every `sync: false`
   variable: `DATABASE_URL`, `GROQ_API_KEY`, `REDDIT_CLIENT_ID`,
   `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, `YOUTUBE_API_KEY`,
   `CORS_ORIGINS`
4. Paste each value (same ones from your local `.env`)
5. Deploy

**Option B — Manual web service:**

1. Render dashboard → New → Web Service → connect repo
2. Runtime: Python 3
3. Build command: `pip install -r requirements.txt`
4. Start command: `python run.py`
5. Add the same environment variables as above, under the service's
   "Environment" tab
6. Deploy

Render injects its own `PORT` at runtime — `run.py` reads it automatically
via `get_server_settings()`, so there's never a port clash between what you
set locally and what Render assigns.

---

## 5. After first deploy

- Render gives you a URL like `https://aspectvoice.onrender.com`
- If you later add a frontend hosted elsewhere, set `CORS_ORIGINS` in
  Render's dashboard to that frontend's exact URL (comma-separated if more
  than one) — until then it can stay empty, which allows all origins
- Free tier spins down after inactivity; first request after idle takes
  ~30–50s to wake up. This is a Render free-tier characteristic, not a bug
  in the app
- Trigger the pipeline the same way as local: `POST /pipeline/run-all` on
  your Render URL instead of `localhost`

---

## 6. Automatic monthly runs (no card, no paid Render cron)

Render's free web-service tier has no free cron job of its own — Render's
own cron job service type bills per-minute and needs a payment method on
file. So this uses a free external pinger instead, with the actual "has a
month really passed" logic kept inside the app itself — the pinger's
schedule doesn't need to be exact.

1. Generate a secret:
   ```bash
   python -c "import secrets; print(secrets.token_hex(16))"
   ```
2. Set `SCHEDULER_SECRET` to that value — in your local `.env` and in
   Render's Environment tab (or the Blueprint prompt in step 4).
3. Sign up free at https://cron-job.org (no card)
4. Create a new cron job:
   - URL: `https://<your-render-url>/pipeline/scheduled-trigger`
   - Method: `POST`
   - Custom header: `X-Scheduler-Secret: <the same secret from step 1>`
   - Schedule: once daily (or a few times a week) — this is just how often
     it *checks*, not how often the pipeline actually runs
5. Done. Every ping is a cheap DB timestamp check; the pipeline itself only
   actually executes once `config.yaml -> schedule.interval_days` (default
   30) has genuinely elapsed since the last scheduled run. As a side
   benefit, the daily ping also keeps the free Render service from
   spinning down as often.

Verify it's working: `GET /pipeline/schedule-status` shows every scheduled
attempt (ran or skipped-as-not-due) with real timestamps — not just a
claim that scheduling is set up.

To change the interval (e.g. every 15 days instead of 30), edit
`config/config.yaml -> schedule.interval_days` — no code change needed.

---

## 7. Troubleshooting

- **`Missing env var X`** on startup → you forgot to set it in `.env`
  (local) or Render's Environment tab (prod). Every required var is listed
  in `.env.example`.
- **DB connection errors after Neon idles** → already handled —
  `pool_pre_ping=True` in `app/models/db.py` transparently reconnects.
- **Review-site scrape returns 0 items** → the site changed its HTML/CSS.
  Selectors live in `config/config.yaml -> sources.review_sites.sites`, no
  code change needed to fix — just re-inspect the live page and update the
  selector.
