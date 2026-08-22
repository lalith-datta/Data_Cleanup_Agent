# Approach & Design Write-up

**AI Agent for Client Data Migration & Integration** — Forward Deployed Engineer take-home.

## What it does

The agent ingests multiple messy employee exports (different column names, mixed date formats, duplicates, missing fields), works out the mapping to a target schema on its own, cleans and validates the data, and pushes each record to a mock target API — pausing for a human only on cases it genuinely can't resolve confidently. A web UI lets a non-technical implementation consultant watch it work, resolve those cases in one glance, and see an audit trail of everything that changed and why.

## Approach: deterministic-first, LLM-last

I treat **determinism as the feature**. In a data-integrity-critical migration, the majority of work — matching `Work Email`/`email_address` to `email`, normalizing `ON LEAVE` → `on_leave`, parsing unambiguous dates, removing exact duplicates — is safely handled by rules and fuzzy matching (RapidFuzz over a schema of field aliases). This path is reproducible, free, and fast.

The LLM (wired through LangChain so any provider — or a local OSS model — can be swapped in by config) is invoked **only** for the small set of genuinely ambiguous decisions rules can't settle. That keeps non-determinism confined to exactly the place where a human reviews the output anyway. When no API key is present, a deterministic MockLLM keeps the whole pipeline working.

Every automated decision carries a **confidence score** (match ratio + rule/validation outcome), and a **threshold** — not the model — decides auto-apply vs. escalate. That single design choice is what turns "an LLM guessing" into an auditable, tunable system.

## How I decided: handle alone vs. escalate

My rule: **the agent acts alone on anything safe and verifiable, and escalates only where a plausible-looking wrong answer is possible.** Concretely, it escalates in five situations:

1. **Ambiguous mapping** — a source column's top-two target candidates are within a small confidence delta (two columns could both be `email`).
2. **Cross-file value conflict** — two files give different non-null values for the same person's field (a work email vs. a personal Gmail). Silently applying last-write-wins here *is* data corruption, so it escalates.
3. **Ambiguous date** — a column where `03/04` could be March or April and files disagree; it escalates the format decision *once*, then applies it column-wide.
4. **Repeated validation failure** — a record that fails validation, gets one auto-fix attempt, and fails again (e.g. an impossible `30/02/1985`).
5. **Unmapped column** — a source column with no confident target (`Grade`), surfaced rather than silently dropped.

I deliberately **do not** escalate the boring majority (high-similarity mappings, whitespace/casing, unambiguous dates, exact duplicates) — that would drown the consultant and defeat the point. The line sits where automating further risks a confident-but-wrong result. Because every auto-decision is audited and thresholds are configurable in-UI, a mis-drawn line is recoverable, not catastrophic — which is what makes the boundary defensible rather than arbitrary.

## Delta on top of the AI

The engineering *around* the model is the actual product: confidence-scored escalation, conflict-detection-on-merge, ambiguous-date detection, idempotent per-record push (keyed on `employee_id`, so retries never duplicate) with retry/rollback, and a complete audit trail of agent and human actions. A naive "throw the files at an LLM" approach passes none of these bars.

## What I'd build next

- **A learning loop:** turn each human correction into a labeled example so future runs auto-resolve the same pattern — the escalation queue shrinks per migration.
- **Reviewer roles + auth** for multi-consultant teams, and richer provenance/versioning.
- **More entity types** (departments, managers) with relationship validation, and a **real target connector** replacing the mock, plus batch-level metrics (STP rate, time-to-resolve) to quantify value per client.
