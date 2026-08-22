# Build Plan — Epics & Tasks

> Companion to `docs/PRD.md`. Hand this to a coding agent. Build in the order below; the **critical path** guarantees a demoable product even if later epics are cut. Each task is written so it can be executed and verified independently.

## Conventions
- **DoD (every task):** code compiles/runs, has a smoke test or manual verification note, and does not break earlier epics.
- **Effort:** S = <1h, M = 1–2h, L = 2–4h (relative, for a coding agent).
- Reference the target schema at `data/target_schema.yaml` and sample files in `data/source/`.

## Critical path (minimum demoable slice)
`Epic 0 → 1 → 2 → 3 → 4 → 5 → 6 → 9 → 10 → 11 → 7 → 13`
(Epics 8 audit and 12 records/audit UI enrich the story; 8 should be woven in from Epic 9 onward.)

---

## Epic 0 — Project scaffolding & infrastructure
**Goal:** runnable skeleton, both apps talk to each other.
- [ ] 0.1 (M) Monorepo layout: `/backend` (FastAPI), `/frontend` (Next.js+TS), `/data` (exists), `/docs` (exists), root README.
- [ ] 0.2 (S) Backend: FastAPI app, `/health` endpoint, CORS for localhost frontend, `uvicorn` run script.
- [ ] 0.3 (S) Dependencies: `fastapi, uvicorn, pydantic v2, pandas, rapidfuzz, python-dateutil, sqlmodel/sqlalchemy, httpx, python-multipart, pyyaml, openpyxl, langchain (+ provider packages), python-dotenv`.
- [ ] 0.4 (S) Frontend: Next.js App Router + Tailwind + shadcn/ui + TanStack Query; `.env` for API base URL.
- [ ] 0.5 (S) DB via SQLModel/SQLAlchemy selected by `DATABASE_URL` (default local SQLite); auto-create tables on startup. Avoid SQLite-only SQL so Supabase/Postgres is a one-line swap later.
- [ ] 0.6 (S) `LLMClient` interface + two impls: `LangChainClient` (provider-agnostic via `init_chat_model` — OpenAI / Anthropic / Groq / Gemini / local, OSS models supported; provider/model/key from env) and `MockLLMClient` (rule-based fallback). Default to Mock when no API key is set.
- [ ] 0.7 (S) Central env config (`.env` + `.env.example`): `DATABASE_URL`, `NEXT_PUBLIC_API_URL`, `LLM_PROVIDER`, `LLM_MODEL`, provider key, `UPLOAD_DIR`. No secrets in code. Storage behind a small adapter (local dir now, Supabase Storage later).

**AC:** `GET /health` returns ok; frontend renders and fetches health; DB created from `DATABASE_URL`; app runs with **no** LLM API key set (uses MockLLM) *and* with a provider key set (LangChain).

## Epic 1 — Data ingestion & profiling
**Goal:** turn uploaded files into normalized in-memory tables + metadata.
- [ ] 1.1 (M) File upload endpoint `POST /api/runs/{id}/files`; persist `source_file` rows (filename, columns, row_count).
- [ ] 1.2 (M) CSV + Excel parser (pandas), UTF-8/encoding-safe; strip fully empty rows.
- [ ] 1.3 (S) Column profiler: dominant type per column (string/number/date/email-like) + sample values.
- [ ] 1.4 (S) Schema loader: parse `target_schema.yaml` into an in-memory `TargetSchema` (fields, types, required, aliases, enum_normalization).

**AC:** uploading the 3 sample files creates 3 `source_file` records with correct columns and counts; profiler flags date-like and email-like columns.

## Epic 2 — Mapping engine (deterministic + LLM adjudication)
**Goal:** source column → target field with confidence.
- [ ] 2.1 (M) Alias/exact matcher (case & whitespace insensitive) → confidence 1.0.
- [ ] 2.2 (M) Fuzzy matcher (RapidFuzz `token_sort_ratio`) vs field names + aliases; return top-N candidates w/ scores.
- [ ] 2.3 (M) Decision function implementing §8 thresholds → `{auto_apply | ambiguous_mapping | unmapped_column}`.
- [ ] 2.4 (M) LLM adjudication for ambiguous/unmapped: prompt returns best target + confidence + 1-line rationale; parse defensively; Mock impl uses fuzzy top-1.
- [ ] 2.5 (S) Persist `field_mapping` rows (method, confidence, status, rationale).

**AC:** on sample data, `DOJ/joined_on/DateOfJoining→date_of_joining`, `Work Email/email_address→email` auto-map; **`Grade`→`unmapped_column`** escalation is produced; `manager` (names) flagged for `manager_unresolved` downstream.

## Epic 3 — Reconciliation & merge
**Goal:** one record per person across files; detect conflicts.
- [ ] 3.1 (M) ID normalization (`E1001`↔`1001`) + match on `match_keys` (email primary, id fallback).
- [ ] 3.2 (M) Field-level merge into target-shaped `record.merged_json`; keep `source_refs_json` (which file gave each value).
- [ ] 3.3 (M) Conflict detection: differing non-null values for same field → `value_conflict` escalation.
- [ ] 3.4 (S) Enrichment: fill missing field from another file when only one file has it (log in audit).

**AC:** Priya (E1001/1001) merges to one record; **email `value_conflict`** raised (work vs gmail) — once payroll's `PersonalEmail` column is mapped to `email` (it doesn't auto-map on its own; see Epic 2's AC); Anita's missing email filled from payroll; exact-duplicate CRM row deduped.

## Epic 4 — Cleaning & normalization
**Goal:** safe auto-fixes; escalate only ambiguous cleans.
- [ ] 4.1 (S) Whitespace trim + casing normalization on all string fields.
- [ ] 4.2 (S) Enum normalization from schema (`ON LEAVE`→`on_leave`, `active `→`active`).
- [ ] 4.3 (M) Per-column date parsing → ISO; **ambiguity detector** (day/month both ≤12 + cross-file disagreement) → `ambiguous_date` escalation applied column-wide on resolve.
- [ ] 4.4 (S) Light phone normalization (strip spaces/dashes, keep leading +).

**AC:** statuses normalized; unambiguous dates → ISO; **Rahul's `03-04-2023` (hr) vs `04/03/2023` (crm)** resolves silently and correctly to 2023-04-03 — each file's own other rows (e.g. Priya's `15-03-2021`, Sara's `11/20/2022`) pin down that file's day/month order, so this isn't actually ambiguous once column evidence is used; a column with no such anchor row anywhere still correctly raises `ambiguous_date` rather than guessing (e.g. Priya's `date_of_birth` before Rahul's own unambiguous DOB row is factored in — verify by checking hr-only columns with zero unambiguous rows).

## Epic 5 — Validation
**Goal:** enforce target schema; escalate hard failures.
- [ ] 5.1 (M) Build Pydantic model from `TargetSchema`; validate each record (required, email, date, enum).
- [ ] 5.2 (S) One auto-fix retry pass; **second failure → `validation_failure` escalation**.
- [ ] 5.3 (S) Set `record.status` (`valid` / `needs_review` / `invalid`).

**AC:** `30/02/1985` (John) fails validation → `validation_failure` escalation; valid records marked `valid`.

## Epic 6 — Escalation engine & confidence boundary
**Goal:** the supervision core.
- [ ] 6.1 (M) Escalation model + create/list/resolve service; statuses open/resolved/rejected.
- [ ] 6.2 (M) Resolution handlers per type (§9) that **re-trigger the minimal affected stage** (mapping→re-merge; date/value→re-clean; record fix→re-validate).
- [ ] 6.3 (S) Column-wide application for `ambiguous_date` and `ambiguous_mapping`.
- [ ] 6.4 (S) STP-rate computation (auto-resolved fields ÷ total) exposed in run stats.

**AC:** resolving a mapping re-runs merge/validate for affected records; STP rate reported; queue empties → run advances to `ready_to_push`.

## Epic 7 — Mock target integration (push / retry / rollback)
**Goal:** integration with audit + recovery.
- [ ] 7.1 (M) Mock target router: `POST /employees` with **deterministic failure** (gmail domain OR missing department → 422); in-memory store.
- [ ] 7.2 (M) Push client: POST each valid record, record `push_result` per record, **idempotent** (key on employee_id — retries don't duplicate).
- [ ] 7.3 (S) Retry endpoint for failed records (respect `max_push_attempts`).
- [ ] 7.4 (M) Rollback endpoint: DELETE pushed records from mock store, mark `record.status=rolled_back`, audit it.

**AC:** on sample data ≥1 record fails (Priya's gmail personal-email case or a missing-dept row); retry after correction succeeds; rollback removes pushed records; all logged.

## Epic 8 — Audit trail (weave in from Epic 3 onward)
**Goal:** complete, inspectable record.
- [ ] 8.1 (S) `audit_log` writer helper (actor, action, target, before/after, reason).
- [ ] 8.2 (S) Instrument every stage + every human resolution + every push/retry/rollback.
- [ ] 8.3 (S) `GET /api/runs/{id}/audit` with filters.

**AC:** audit log shows a coherent story for one record end-to-end (mapped → cleaned → conflict-resolved-by-human → pushed).

## Epic 9 — Orchestrator & API surface
**Goal:** wire engines into the state machine + REST.
- [ ] 9.1 (L) Pipeline orchestrator implementing the §7 state machine as an async background task; parks at `awaiting_review`.
- [ ] 9.2 (M) Implement all endpoints in PRD §10.
- [ ] 9.3 (S) Activity feed store + `GET .../activity?since=` for live-view polling.
- [ ] 9.4 (S) Run stats endpoint (status, counts, STP rate).

**AC:** `POST /start` runs the full pipeline on sample files and parks with open escalations; resolving all → `ready_to_push`; every endpoint returns sane payloads.

## Epic 10 — Frontend: Live View
- [ ] 10.1 (M) New Migration screen (name + drag-drop upload + Start).
- [ ] 10.2 (M) Pipeline stepper + activity feed (TanStack Query polling 1–2s).
- [ ] 10.3 (S) Stats strip: STP %, records, escalations open/resolved, pushed/failed.

**AC:** user uploads sample files, starts, and watches the feed + stats update live to `awaiting_review`.

## Epic 11 — Frontend: Escalation Queue & resolution
- [ ] 11.1 (M) Queue list with type badges + open count.
- [ ] 11.2 (L) Per-type resolution cards (§9) with one-glance context + **Approve / Correct / Reject**.
- [ ] 11.3 (S) Optimistic update + refetch; queue decrements; advances run when empty.

**AC:** every escalation type renders with enough context to resolve in one glance; resolving updates backend and UI; demo escalation (email conflict) resolvable live.

## Epic 12 — Frontend: Records, Push & Audit
- [ ] 12.1 (M) Records table (filter by status) + expandable row showing merged record + per-field provenance.
- [ ] 12.2 (M) Push & Results panel: per-record status, Retry failed, Rollback.
- [ ] 12.3 (S) Audit Log view (chronological, filter by actor/action).

**AC:** push runs from UI; failing record visible; retry + rollback work from UI; audit readable by a non-technical user.

## Epic 13 — Seed data, demo, README & polish
- [ ] 13.1 (S) Seed/reset script to load the 3 sample files into a fresh run for demos.
- [ ] 13.2 (M) README: setup, tech stack, env vars (`.env.example`), local run instructions, sample-data walkthrough, escalation-boundary rationale, and the optional cloud path (Supabase + Vercel/Render).
- [ ] 13.3 (S) 1-page write-up (approach + autonomy-vs-escalate reasoning + "what I'd build next"), reuse `Delta over vanilla AI` points.
- [ ] 13.4 (S) Record demo showing ≥1 escalation resolved end-to-end.
- [ ] 13.5 (S) Graceful-degradation check: full run works with MockLLM (no LLM API key) *and* with a real provider via LangChain.

**AC:** a fresh clone runs with documented steps and reproduces the demo including a resolved escalation.

---

## Epic 14 — (Optional, time-permitting) Cloud adoption
**Goal:** flip the local-first build to hosted with config, not rewrite. Off the critical path.
- [ ] 14.1 (S) Point `DATABASE_URL` at Supabase Postgres; create schema; verify a full run persists.
- [ ] 14.2 (S) Swap storage adapter local dir → Supabase Storage for uploads.
- [ ] 14.3 (S) Deploy frontend to Vercel; set `NEXT_PUBLIC_API_URL`.
- [ ] 14.4 (M) Deploy FastAPI to Render/Railway/Fly (persistent process for the park/resume agent); set env + provider key.
- [ ] 14.5 (S) Smoke-test hosted demo end-to-end incl. one escalation + one push failure.

**AC:** hosted link runs the sample demo with a resolved escalation; no code changes beyond env/config.

## Suggested milestones
| Milestone | Epics | Outcome |
|---|---|---|
| **M1 – Agent core (headless)** | 0–6, 8, 9 | Pipeline runs on sample data via API, produces correct escalations + STP rate. |
| **M2 – Supervision UI** | 10, 11 | Consultant can watch + resolve escalations. |
| **M3 – Integration & recovery** | 7, 12 | Push/retry/rollback + records/audit views. |
| **M4 – Demo-ready** | 13 | README, write-up, recording, graceful degradation. |

## Risk guardrails for the agent
- If no LLM API key is set, **do not block** — MockLLM keeps deterministic mapping working (Epic 0.6 / 13.5).
- **Local-first:** don't build serverless/cloud infra now; keep everything env-driven so cloud is a later config step (Epic 14 / PRD §5 deployment posture).
- Keep the **deterministic path fully reproducible**; the LLM must never touch the safe majority.
- Ensure the sample data **always** yields ≥1 escalation and ≥1 push failure (demo depends on it).
