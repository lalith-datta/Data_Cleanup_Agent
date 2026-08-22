# AI Agent for Client Data Migration & Integration

An agent that ingests messy, multi-file **employee** exports, autonomously **maps → cleans → validates** them against a target schema, pushes the result to a **mock target API**, and **escalates only genuinely ambiguous cases** to a non-technical implementation consultant through a supervision UI — with a full audit trail.

> **The core idea:** autonomy is only trustworthy if uncertainty is visible. The agent does the safe majority alone and asks smart, well-scoped questions about the rest — it never guesses silently on data it isn't sure about.

Built for the Darwinbox **Forward Deployed Engineer** take-home. See [`docs/PRD.md`](docs/PRD.md) for the full spec and [`docs/EPICS.md`](docs/EPICS.md) for the build plan.

---

## Highlights

- **Multi-file reconciliation** — merges 3 exports with different headers/formats into one dataset, matching people across files (handles `E1001` ↔ `1001` id mismatches).
- **Deterministic-first, LLM-last** — rules + fuzzy matching handle the safe ~90%; an LLM (via LangChain) adjudicates only genuine ambiguity. Reproducible, cheap, fast.
- **Defensible escalation boundary** — escalates only where a plausible-looking wrong answer is possible: ambiguous mappings, cross-file value conflicts, ambiguous dates, twice-failed validations, unmapped columns.
- **Human-in-the-loop UI** — live activity feed, a one-glance escalation queue, and approve / correct / reject.
- **Idempotent integration** — per-record push to a mock API with retry + rollback, keyed on `employee_id` so retries never duplicate.
- **Full audit trail** — every agent decision and human override, with rationale + confidence.

## Architecture

```
Next.js (Vercel-ready)  ──REST + poll──▶  FastAPI backend
   Live View                                 ├─ Pipeline orchestrator (state machine)
   Escalation Queue                          ├─ Engines: ingest / map / reconcile / clean / validate
   Records + Push + Audit                    ├─ Escalation engine (confidence boundary)
                                             ├─ LLMClient  ──▶  LangChain (provider-agnostic) | MockLLM
                                             ├─ Push client ──▶  Mock target API (deterministic failures)
                                             └─ SQLite (DATABASE_URL → Postgres/Supabase later)
```

Pipeline: `Ingest → Map → Reconcile → Clean → Validate → [awaiting review ⇄ human] → Push → Audit`.

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | Next.js (App Router) · TypeScript · TailwindCSS · shadcn/ui · TanStack Query (polling) |
| Backend | FastAPI (Python 3.11+) · Pydantic v2 |
| Data | Pandas · RapidFuzz · python-dateutil |
| AI | **LangChain** provider-agnostic (`init_chat_model`) behind an `LLMClient` interface; MockLLM fallback |
| Persistence | SQLite (default) via SQLModel/SQLAlchemy, selected by `DATABASE_URL` |
| Mock target | FastAPI router with deterministic failures |

## Repository layout

```
.
├── backend/            # FastAPI app: engines/, services/, routers/, llm/, scripts/
├── frontend/           # Next.js supervision UI (app/, components/, lib/)
├── data/
│   ├── target_schema.yaml
│   └── source/{hr_export,crm_export,payroll_export}.csv
├── docs/
│   ├── PRD.md          # full product + technical spec
│   ├── EPICS.md        # epics & task breakdown for the coding agent
│   └── WRITEUP.md      # 1-page approach write-up (deliverable)
├── .env.example
└── README.md
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- (Optional) An LLM provider API key. **Not required** — without one, the app uses the deterministic MockLLM and still runs end-to-end.

## Setup

```bash
# 1. Clone + configure
cp .env.example backend/.env      # backend env (defaults work as-is)
# frontend reads NEXT_PUBLIC_API_URL from frontend/.env.local (already set for local dev)

# 2. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows PowerShell (Unix: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

### Quick demo (deterministic)

```bash
# with the backend STOPPED:
cd backend
python scripts/seed_demo.py       # loads the 3 sample files into a fresh run

# start backend + frontend, open http://localhost:3000, open the seeded run,
# press Start. To verify the whole flow headlessly instead:
python scripts/e2e_demo.py        # requires backend running on :8000
```

## Configuration (env)

All environment-specific values are injected via env vars so cloud adoption is *configuration, not migration*. See [`.env.example`](.env.example) for the full list. Key ones:

| Var | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | DB connection | `sqlite:///./migration.db` |
| `LLM_PROVIDER` / `LLM_MODEL` | Model selection via LangChain | unset → MockLLM |
| `<PROVIDER>_API_KEY` | Provider credential | unset |
| `NEXT_PUBLIC_API_URL` | Frontend → backend base URL | `http://localhost:8000` |
| `UPLOAD_DIR` | Local file storage | `./uploads` |
| `AUTO_APPLY_THRESHOLD` / `MIN_MAP_THRESHOLD` / `AMBIGUOUS_DELTA` | Escalation tuning | `0.90 / 0.70 / 0.08` |

## Sample data walkthrough

`data/source/` contains three deliberately messy exports engineered to exercise every behavior. Each planted quirk maps to a specific agent action:

| Planted case | Agent behavior |
|---|---|
| Different headers (`Emp ID` / `id` / `EmployeeCode`) | Fuzzy auto-map (STP) |
| `E1001` vs `1001` id formats | Reconcile on **email**, id normalized to digits-only as fallback |
| Per-file date conventions (hr=dd/mm, crm=mm/dd, e.g. `15-03-2021` / `03/15/2021`) | Each file's own unambiguous rows pin down its convention (§7.4) — auto-normalized silently, including rows that look ambiguous in isolation (Rahul's `03-04-2023` vs `04/03/2023` agree once each file's convention is known) |
| `PersonalEmail` (payroll) — no confident target on its own (56%, below the auto-map threshold) | **Escalate** unmapped column — mapping it to `email` is also what surfaces the next row |
| Work vs personal email (Priya), once `PersonalEmail` → `email` is resolved | **Escalate** value conflict |
| `Grade` (L5/L6/L7) and `BankName`, no clear target | **Escalate** unmapped column |
| `EmploymentType` (Full-time) — fuzzy-close to both `full_name` and `employment_status` | **Escalate** ambiguous mapping (neither candidate is actually right — dropping is the defensible call) |
| `manager` as a name, not email | **Escalate** manager-unresolved |
| Missing email in HR, present in payroll (Anita, Vikram) | Cross-file enrichment — happens once `PersonalEmail` is mapped |
| `30/02/1985` invalid date (John) | Fails validation → **escalate** |
| Exact duplicate CRM row | Auto-dedupe (STP) |

**Result on screen:** STP rate in the 80s + roughly 9 escalations, each still resolvable in one glance — more than the "3–5" target because payroll alone contributes 4 mapping-level ones on top of the record-level cases above.

## Escalation boundary — why the line is here

The agent acts alone on anything **safe and verifiable** (high-similarity header matches, deterministic cleans, exact-duplicate removal) and escalates only where a **plausible-looking wrong answer is possible**. Thresholds (in `.env`) make the boundary explicit and tunable; because every auto-decision is audited, a mis-set threshold is recoverable, not catastrophic. Full rationale in [`docs/PRD.md` §8](docs/PRD.md) and [`docs/WRITEUP.md`](docs/WRITEUP.md).

## API summary

`POST /api/runs` · `POST /api/runs/{id}/files` · `POST /api/runs/{id}/start` · `GET /api/runs/{id}` · `GET /api/runs/{id}/activity` · `GET /api/runs/{id}/escalations` · `POST /api/escalations/{id}/resolve` · `GET /api/runs/{id}/records` · `POST /api/runs/{id}/push` · `POST /api/runs/{id}/push/retry` · `POST /api/runs/{id}/rollback` · `GET /api/runs/{id}/audit`. Full contract in [`docs/PRD.md` §10](docs/PRD.md).

## Demo script

1. Upload the 3 sample files → **Start**.
2. Watch the live feed auto-map & clean the safe majority (STP % climbs to ~80%+).
3. Escalation queue shows ~9 items → resolve **`PersonalEmail` (unmapped column)** by mapping it to `email` — watch this surface a *new* **email conflict** escalation (work vs. personal), which wasn't there a moment ago, demonstrating the re-trigger-on-resolve mechanism live. Resolve that conflict (pick work email), then the **`Grade` unmapped column** (drop).
4. **Push** → one record fails (missing dept — Vikram, payroll-only) → **Retry** / show **Rollback**.
5. Open the **Audit Log** to show the full record of what changed and why.

## Optional: cloud path (time-permitting)

The build is local-first but cloud-ready. To host later (no code changes, just config — see Epic 14):
- `DATABASE_URL` → Supabase Postgres; uploads → Supabase Storage.
- Frontend → **Vercel** (`NEXT_PUBLIC_API_URL` = deployed backend).
- Backend → **Render / Railway / Fly** (persistent process for the park/resume agent — *not* Vercel serverless).

## What I'd build next

Turn human corrections into labeled examples so future runs auto-resolve those patterns (a data-quality flywheel that shrinks the escalation queue over time); add reviewer roles/auth; support additional entity types and a real target connector. See [`docs/WRITEUP.md`](docs/WRITEUP.md).
