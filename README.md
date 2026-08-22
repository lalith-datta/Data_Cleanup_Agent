# AI Agent for Client Data Migration & Integration

An agent that ingests messy, multi-file exports, autonomously **maps → cleans → validates** them against a target schema, pushes the result to a target system, and **escalates only genuinely ambiguous cases** to a non-technical implementation consultant through a supervision UI — with a full audit trail.

> **The core idea:** autonomy is only trustworthy if uncertainty is visible. The agent does the safe majority alone and asks smart, well-scoped questions about the rest — it never guesses silently on data it isn't sure about.

The default fixture models employee data, but each migration can use its own YAML or JSON target schema. See [`docs/PRD.md`](docs/PRD.md) for the full specification and [`docs/EPICS.md`](docs/EPICS.md) for the build plan.

---

## Highlights

- **Schema-driven migration** — upload a YAML or JSON target schema for a run, preview its parsed fields before starting, and use the schema's own entity, match keys and primary key.
- **Multi-file reconciliation** — merges exports with different headers/formats into one dataset, matching records across files (the employee fixture handles `E1001` ↔ `1001` id mismatches).
- **Deterministic-first, LLM-last** — rules + fuzzy matching handle the safe ~90%; an LLM (via LangChain) adjudicates only genuine ambiguity. Reproducible, cheap, fast.
- **Defensible escalation boundary** — escalates only where a plausible-looking wrong answer is possible: ambiguous mappings, cross-file value conflicts, ambiguous dates, twice-failed validations, unmapped columns.
- **Human-in-the-loop UI** — live activity feed, a one-glance escalation queue, and approve / correct / reject.
- **Safe delivery** — per-record, idempotent delivery keyed on the configured schema primary key, with partial-send counts, targeted retry for failed records and rollback.
- **Full audit trail** — every agent decision and human override, with rationale + confidence.

## Architecture

```
Next.js (Vercel-ready)  ──REST + poll──▶  FastAPI backend
   Live View                                 ├─ Pipeline orchestrator (state machine)
   Escalation Queue                          ├─ Engines: ingest / map / reconcile / clean / validate
   Records + Push + Audit                    ├─ Escalation engine (confidence boundary)
                                             ├─ LLMClient  ──▶  LangChain (provider-agnostic) | MockLLM
                                             ├─ Push client ──▶  Target connector / mock target API
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
| Target integration | FastAPI mock target with deterministic demo failures; primary-key-aware push interface |

## Repository layout

```
.
├── backend/            # FastAPI app: engines/, services/, routers/, llm/, scripts/
├── frontend/           # Next.js supervision UI (app/, components/, lib/)
├── data/
│   ├── target_schema.yaml
│   ├── source/{hr_export,crm_export,payroll_export}.csv
│   └── examples/customer_migration/  # custom-schema YAML + sample CSVs
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
| `TARGET_SCHEMA_PATH` | Default schema when a run has no uploaded schema | `../data/target_schema.yaml` |
| `AUTO_APPLY_THRESHOLD` / `MIN_MAP_THRESHOLD` / `AMBIGUOUS_DELTA` | Escalation tuning | `0.90 / 0.70 / 0.08` |

## Custom target schemas

When starting a migration, optionally upload a `.yaml`, `.yml` or `.json`
schema in the **Custom target schema** panel. The application validates and
previews the parsed entity, primary key, match keys and fields before the run
starts. The uploaded schema drives mapping, cleaning, validation,
reconciliation and delivery for that run.

Schemas may be a full specification or a minimal list of field names. A full
example for a customer migration, along with three intentionally varied source
files, is available in [`data/examples/customer_migration/`](data/examples/customer_migration/).

