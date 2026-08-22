# Deployment — Supabase + Render + Vercel

This app has three pieces that deploy to three hosts. This is deliberate.

```
 Browser ──▶ Vercel (Next.js frontend)
                 │  REST + polling (CORS)
                 ▼
            Render (FastAPI agent — persistent process)
                 │  DATABASE_URL
                 ▼
            Supabase (Postgres)
```

**Why not everything on Vercel?** Vercel *can* run Python/FastAPI, but only as
**serverless functions** — each request runs in a function that is killed the moment
it returns a response. This app can't live under that model for two concrete reasons:

1. **The agent runs as a background task that outlives the request.** `start_pipeline`
   does `asyncio.create_task(_execute(run_id))` and returns immediately; the pipeline
   keeps working (and parks at *awaiting review* for minutes) after the response. On
   serverless, that response return kills the function — the pipeline never finishes.
2. **Critical state lives in process memory**, not the DB: the mock target's
   in-memory store (`_store`) and the active-pipeline registry (`_running`). Serverless
   routes each request to a possibly-different, cold instance, so a push and its
   rollback would hit different empty instances.

So the frontend (Next.js) goes on Vercel, and the Python agent goes on a **persistent
host** (Render). Making the backend serverless would mean adding a job queue
(Inngest/QStash), moving all state into Postgres, and per-request idempotency — the
right call at scale, deliberately out of scope for this MVP.

Everything is env-driven, so this is **configuration, not code changes**.

---

## Prerequisites

- The repo pushed to GitHub.
- Free accounts: [Supabase](https://supabase.com), [Render](https://render.com),
  [Vercel](https://vercel.com).

---

## Step 1 — Database on Supabase (~3 min)

1. **New project** → pick a name, set a strong database password (save it), choose a region.
2. Wait for it to provision.
3. **Project Settings → Database → Connection string → "Session pooler"** tab.
   - Use the **Session pooler** (IPv4, works with SQLAlchemy's long-lived pool).
     Do **not** use the *Transaction* pooler (port 6543) — it breaks prepared
     statements.
   - It looks like:
     `postgresql://postgres.abcd1234:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres`
4. Turn it into the `DATABASE_URL` the backend expects — add `+psycopg` and `?sslmode=require`:
   ```
   postgresql+psycopg://postgres.abcd1234:YOUR-PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require
   ```
   Keep this for Step 2. (Tables are created automatically on first backend boot —
   no migration step needed.)

---

## Step 2 — Backend on Render (~5 min)

You can deploy from the included Blueprint (`render.yaml` at the repo root) or set it
up manually. Manual is fine:

1. **New → Web Service → Build and deploy from a Git repository** → pick this repo.
2. Set:
   - **Root Directory:** `backend` (important — the FastAPI app lives there)
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
3. **Environment** → add (from `backend/.env.production.example`):
   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | the Supabase string from Step 1 |
   | `CORS_ORIGINS` | `*` for now (tighten to the Vercel URL in Step 4) |
   | `LLM_PROVIDER` | leave empty (uses deterministic MockLLM) |
   | `PYTHON_VERSION` | `3.12.0` |
   > Do **not** set `PORT`/`BACKEND_PORT` — Render injects `$PORT` and the start
   > command already reads it.
4. **Create Web Service** and wait for the first deploy.
5. Verify: open `https://<your-service>.onrender.com/health` →
   `{"status":"ok","db":"postgresql","llm":"mock"}`. The `db` field confirms it's
   talking to Supabase.

> **Heads-up on the free plan:** Render free services **spin down after ~15 min idle**
> and take ~50s to cold-start on the next request — a reviewer clicking your link cold
> would wait. Options: (a) hit the URL yourself ~1 min before demoing to warm it;
> (b) a free uptime pinger (UptimeRobot / cron-job.org) hitting `/health` every ~10 min
> keeps it awake; (c) upgrade to the **Starter** plan (~$7/mo) to stay always-on.

---

## Step 3 — Frontend on Vercel (~3 min)

1. **Add New → Project → Import** this repo.
2. **Root Directory → `frontend`.** Framework preset auto-detects **Next.js**.
3. **Environment Variables** → add:
   | Key | Value |
   |-----|-------|
   | `NEXT_PUBLIC_API_URL` | `https://<your-service>.onrender.com` (no trailing slash) |
4. **Deploy.** Note the resulting URL, e.g. `https://your-app.vercel.app`.

---

## Step 4 — Connect them (CORS) (~1 min)

1. Back in **Render → Environment**, set `CORS_ORIGINS` to your exact Vercel URL
   (e.g. `https://your-app.vercel.app`) and redeploy. (Leaving `*` also works —
   the app uses no cookies/auth — but pinning is tidier.)
2. Open the Vercel URL. The home page should show **"Connected"**.

---

## Step 5 — Seed a demo & verify (~2 min)

Two ways to get data in:

- **Via the UI (simplest):** on the home page, create a migration and upload the
  three sample files from `data/source/` (`hr_export.csv`, `crm_export.csv`,
  `payroll_export.csv`), then press Start.
- **Via a one-off script:** Render → your service → **Shell** tab, then:
  ```
  python scripts/seed_demo.py
  ```
  Open the seeded run in the UI and press Start.

Walk the demo: watch the agent work → answer the questions → **Send** → one record
fails (deterministic) → **Try again** → **All done**.

---

## Environment variable reference

| Where | Key | Purpose |
|-------|-----|---------|
| Render | `DATABASE_URL` | Supabase Postgres (session pooler, `+psycopg`, `sslmode=require`) |
| Render | `CORS_ORIGINS` | allowed frontend origin(s); `*` or the Vercel URL |
| Render | `LLM_PROVIDER` / `LLM_MODEL` / `*_API_KEY` | optional — enable a real LLM; empty = MockLLM |
| Render | `UPLOAD_DIR` | local ephemeral upload dir (default `./uploads`) |
| Render | `PYTHON_VERSION` | pin the runtime (`3.12.0`) |
| Vercel | `NEXT_PUBLIC_API_URL` | the Render backend URL |

---

## Gotchas & troubleshooting

- **`/health` shows `db: sqlite`** → `DATABASE_URL` wasn't picked up. Check the
  Render env var and that it starts with `postgresql+psycopg://`.
- **DB connection errors / SSL** → ensure `?sslmode=require` is on the URL and
  you used the **Session** pooler (not Transaction/6543).
- **Frontend shows "Offline" / CORS errors in the browser console** →
  `NEXT_PUBLIC_API_URL` is wrong, or `CORS_ORIGINS` doesn't include the Vercel URL.
- **Uploads vanish after a redeploy** → expected: `UPLOAD_DIR` is ephemeral on
  Render. It's fine within a single run (upload + processing happen together).
  For durable storage across restarts, move to Supabase Storage (a `SupabaseStorage`
  adapter behind the existing `StorageAdapter` interface — a phase-2 enhancement).
- **First request after idle is slow (~50s)** → Render free plan spun the service
  down. Warm it before demoing, add a free uptime pinger on `/health`, or use the
  Starter plan (see the heads-up in Step 2).

---

## Local development is unchanged

None of this affects local dev. With no `DATABASE_URL`, the app uses SQLite and runs
exactly as before:

```
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

---

## Appendix — Verify the Postgres path before deploying (optional, ~2 min)

You don't need Docker. Point the backend at a real Postgres and run the checker.
**Easiest: use the Supabase project from Step 1 as the test target** (it's the real
thing you'll deploy against).

### Option A — against Supabase directly (recommended)

PowerShell (Windows):
```powershell
cd backend
# (first time on this machine) python -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://postgres.REF:PWD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require"
.\.venv\Scripts\python.exe scripts\verify_postgres.py
```

bash (macOS/Linux):
```bash
cd backend
# (first time) python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://postgres.REF:PWD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require"
python scripts/verify_postgres.py
```

Expected:
```
→ Driver:  postgresql+psycopg
→ Target:  aws-0-REGION.pooler.supabase.com
✅ Postgres path verified — driver, SSL, table creation, and JSON columns all work.
```

Optionally run the full agent against Postgres too: keep `DATABASE_URL` set, start the
backend (`uvicorn app.main:app --port 8000`), then in another shell run
`python scripts/e2e_demo.py`. It should print `E2E OK`.

### Option B — against a local Docker Postgres (offline, needs Docker running)

```bash
docker run --name mig-pg -e POSTGRES_PASSWORD=pw -p 5432:5432 -d postgres:16
export DATABASE_URL="postgresql+psycopg://postgres:pw@localhost:5432/postgres"
python scripts/verify_postgres.py
docker rm -f mig-pg   # cleanup
```

The verify script creates the schema, does a write/read/delete round-trip, and cleans
up after itself — it leaves no test data behind.

