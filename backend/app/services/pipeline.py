"""Pipeline service: the re-runnable stage logic (Epics 2.5, 3, 4, 5).

The orchestrator (Epic 9) runs these in order; escalation resolution
(Epic 6) re-runs only the downstream half. Both paths share this code so
behavior is identical whether the agent or a human resolution drives it.
"""

from datetime import datetime, timezone

from sqlmodel import Session, select

from ..engines.clean import clean_record
from ..engines.ingest import parse_file, profile_columns
from ..engines.mapping import decide_mapping
from ..engines.reconcile import (
    SourceRow,
    apply_inferred_formats,
    infer_source_date_formats,
    reconcile,
)
from ..engines.schema_loader import load_target_schema
from ..engines.validate import auto_fix, validate_record
from ..llm import get_llm_client
from ..models import AuditLog, Escalation, FieldMapping, MigrationRun, Record, SourceFile
from ..services.audit import audit
from .escalations import find_open, raise_escalation


def _touch(run: MigrationRun) -> None:
    run.updated_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------- mapping
async def run_mapping_stage(session: Session, run: MigrationRun) -> None:
    schema = load_target_schema()
    run.status = "mapping"
    _touch(run)
    session.add(run)

    files = session.exec(
        select(SourceFile).where(SourceFile.run_id == run.id)
    ).all()
    llm = get_llm_client()

    for sf in files:
        df = parse_file(sf.stored_path)
        profile = profile_columns(df)
        for col in sf.columns_json:
            decision = decide_mapping(col, schema)
            samples = profile.get(col, {}).get("samples", [])

            if decision.decision == "auto_apply":
                session.add(
                    FieldMapping(
                        run_id=run.id,
                        source_file_id=sf.id,
                        source_column=col,
                        target_field=decision.target_field,
                        method=decision.method,
                        confidence=decision.confidence,
                        status="auto_applied",
                        rationale=decision.rationale,
                        candidates_json=decision.candidates,
                    )
                )
                audit(
                    session, run.id, "agent", "mapped_column",
                    "column", f"{sf.filename}:{col}",
                    after={"target": decision.target_field,
                           "confidence": decision.confidence},
                    reason=decision.rationale,
                )

            elif decision.decision == "ambiguous_mapping":
                fm = FieldMapping(
                    run_id=run.id,
                    source_file_id=sf.id,
                    source_column=col,
                    method="fuzzy",
                    confidence=decision.confidence,
                    status="escalated",
                    rationale=decision.rationale,
                    candidates_json=decision.candidates,
                )
                session.add(fm)
                session.flush()
                raise_escalation(
                    session, run.id, "ambiguous_mapping",
                    entity_ref=f"{sf.filename}:{col}",
                    context={"source_column": col, "file": sf.filename,
                             "samples": samples},
                    options=decision.candidates,
                    confidence=decision.confidence,
                )

            else:  # below fuzzy min -> LLM adjudicates, else unmapped_column
                suggestion = await llm.suggest_mapping(
                    col, samples, schema.field_names()
                )
                if (
                    suggestion
                    and suggestion.target_field
                    and suggestion.confidence >= run.config_json.get(
                        "auto_apply_threshold", 0.90
                    )
                ):
                    session.add(
                        FieldMapping(
                            run_id=run.id,
                            source_file_id=sf.id,
                            source_column=col,
                            target_field=suggestion.target_field,
                            method="llm",
                            confidence=suggestion.confidence,
                            status="auto_applied",
                            rationale=f"llm: {suggestion.rationale}",
                        )
                    )
                    audit(
                        session, run.id, "agent", "mapped_column",
                        "column", f"{sf.filename}:{col}",
                        after={"target": suggestion.target_field,
                               "confidence": suggestion.confidence},
                        reason=f"llm adjudication: {suggestion.rationale}",
                    )
                else:
                    fm = FieldMapping(
                        run_id=run.id,
                        source_file_id=sf.id,
                        source_column=col,
                        method="llm",
                        confidence=suggestion.confidence if suggestion else 0.0,
                        status="escalated",
                        rationale=(suggestion.rationale if suggestion
                                   else "llm returned no confident suggestion"),
                        candidates_json=decision.candidates,
                    )
                    session.add(fm)
                    session.flush()
                    raise_escalation(
                        session, run.id, "unmapped_column",
                        entity_ref=f"{sf.filename}:{col}",
                        context={"source_column": col, "file": sf.filename,
                                 "samples": samples},
                        options=decision.candidates,
                        confidence=decision.confidence,
                    )
    session.commit()


# ------------------------------------------- reconcile -> clean -> validate
def run_downstream_stages(session: Session, run: MigrationRun) -> None:
    """Rebuild records from current mappings, then clean + validate.
    Idempotent pre-push: existing records for the run are replaced."""
    schema = load_target_schema()

    mappings = session.exec(
        select(FieldMapping).where(
            FieldMapping.run_id == run.id,
            FieldMapping.status.in_(["auto_applied", "resolved"]),
            FieldMapping.target_field.is_not(None),
        )
    ).all()
    by_file: dict[int, dict[str, str]] = {}
    for m in mappings:
        by_file.setdefault(m.source_file_id, {})[m.source_column] = m.target_field

    files = session.exec(
        select(SourceFile).where(SourceFile.run_id == run.id)
    ).all()

    # rebuild records (safe pre-push only)
    existing = session.exec(select(Record).where(Record.run_id == run.id)).all()
    for r in existing:
        session.delete(r)
    session.flush()

    rows: list[SourceRow] = []
    for sf in files:
        col_map = by_file.get(sf.id, {})
        df = parse_file(sf.stored_path)
        for i, raw in df.iterrows():
            vals = {
                col_map[c]: str(raw[c])
                for c in df.columns
                if c in col_map and str(raw[c]) != "nan"
            }
            rows.append(SourceRow(file=sf.filename, row_index=int(i), values=vals))

    run.status = "reconciling"
    _touch(run)
    session.add(run)
    session.commit()  # so pollers can actually observe this stage

    forced_formats: dict[str, str] = run.config_json.get("forced_formats", {})
    # Infer each file's own date-column convention from its own unambiguous
    # rows (PRD §7.4) BEFORE merging, so files that already agree once their
    # own formats are known never reach the conflict/ambiguity machinery.
    inferred_formats = infer_source_date_formats(rows, schema)
    rows = apply_inferred_formats(rows, inferred_formats)
    merged_results = reconcile(rows, schema, forced_formats)

    run.status = "cleaning"
    _touch(run)
    session.add(run)
    session.commit()

    ambiguous_by_field: dict[str, dict] = {}

    run.status = "validating"
    _touch(run)
    session.add(run)
    session.commit()

    known_emails = {
        r.merged.get("email") for r in merged_results if r.merged.get("email")
    }

    # record-level escalations re-raised this pass; anything previously open
    # that does NOT recur is auto-closed (its condition no longer holds)
    restill_open: set[int] = set()
    manual_overrides: dict[str, dict[str, str | None]] = run.config_json.get(
        "manual_overrides", {}
    )

    for res in merged_results:
        overrides = manual_overrides.get(res.natural_key, {})
        cr = clean_record(res.merged, res.provenance, schema, forced_formats)
        for a in cr.ambiguous_dates:
            slot = ambiguous_by_field.setdefault(
                a["field"], {"field": a["field"], "samples": [], "options": a["options"]}
            )
            if a["raw"] not in slot["samples"]:
                slot["samples"].append(a["raw"])

        fixed, fixes = auto_fix(cr.cleaned, schema)
        # re-apply manual human edits so they survive the rebuild
        for fname, oval in overrides.items():
            fixed[fname] = oval
        errors = validate_record(fixed, schema)
        # a field awaiting an ambiguous_date decision fails ISO validation by
        # definition — suppress that duplicate; the date escalation owns it
        pending_date_fields = {a["field"] for a in cr.ambiguous_dates}
        errors = [e for e in errors if e.field not in pending_date_fields]

        rec = Record(
            run_id=run.id,
            natural_key=res.natural_key,
            merged_json=fixed,
            source_refs_json=res.provenance,
            status="valid",
        )
        session.add(rec)
        session.flush()

        for change in cr.changes + fixes:
            audit(
                session, run.id, "agent", "cleaned_value",
                "record", res.natural_key,
                before={change["field"]: change.get("before")},
                after={change["field"]: change.get("after")},
                reason=change["reason"],
            )

        # value conflicts -> escalate (entity_ref includes field so multiple
        # conflicts on the same record each surface); fields with a stored
        # human override are already settled — don't re-raise
        for conflict in res.conflicts:
            if conflict["field"] in overrides:
                continue
            if conflict.get("date_format_question"):
                # a format question, not a value dispute — fold into the
                # same column-wide ambiguous_date flow clean.py feeds
                slot = ambiguous_by_field.setdefault(
                    conflict["field"],
                    {"field": conflict["field"], "samples": [], "options": []},
                )
                for v in conflict["values"]:
                    if v["value"] not in slot["samples"]:
                        slot["samples"].append(v["value"])
                for opt in conflict.get("date_options", []):
                    if opt not in slot["options"]:
                        slot["options"].append(opt)
                rec.status = "needs_review"
                continue
            esc = raise_escalation(
                session, run.id, "value_conflict",
                entity_ref=f"{res.natural_key}:{conflict['field']}",
                context={"record": res.natural_key, "field": conflict["field"],
                         "values": conflict["values"]},
                options=[{"value": v["value"], "source": v["file"]}
                         for v in conflict["values"]],
            )
            restill_open.add(esc.id)
            rec.status = "needs_review"

        # manager value that isn't an email -> manager_unresolved w/ matches
        mgr = fixed.get("manager_email")
        if mgr and "@" not in str(mgr) and "manager_email" not in overrides:
            from rapidfuzz import process as rf_process

            matches = rf_process.extract(
                str(mgr), sorted(known_emails), limit=3,
            ) if known_emails else []
            esc = raise_escalation(
                session, run.id, "manager_unresolved",
                entity_ref=res.natural_key,
                context={"record": res.natural_key, "manager_name": mgr},
                options=[{"value": m[0], "score": round(m[1] / 100, 3)}
                         for m in matches],
            )
            restill_open.add(esc.id)
            rec.status = "needs_review"

        # hard validation failures -> escalate (manager handled above)
        for err in errors:
            if err.field == "manager_email":
                continue
            esc = raise_escalation(
                session, run.id, "validation_failure",
                entity_ref=f"{res.natural_key}:{err.field}",
                context={"record": res.natural_key, "field": err.field,
                         "value": err.value, "error": err.error},
                options=[],
            )
            restill_open.add(esc.id)
            rec.status = "needs_review"

        session.add(rec)
        session.commit()

    # one ambiguous_date escalation per field (resolve once, apply field-wide)
    for fname, info in ambiguous_by_field.items():
        if fname in forced_formats:
            continue
        esc = raise_escalation(
            session, run.id, "ambiguous_date",
            entity_ref=fname,
            context={"field": fname, "samples": info["samples"]},
            options=info["options"],
        )
        restill_open.add(esc.id)

    # auto-close record-level escalations whose condition cleared on re-run
    _auto_close_stale(session, run, restill_open)

    _recompute_stats(session, run)
    _set_gate_status(session, run)
    session.commit()


def _auto_close_stale(
    session: Session, run: MigrationRun, still_open: set[int]
) -> None:
    """Record-level escalations that didn't recur on re-run auto-close —
    their condition no longer holds (e.g. a mapping resolution fixed the
    underlying value). Mapping escalations are excluded: only a human
    decision resolves those."""
    auto_types = ("value_conflict", "validation_failure", "ambiguous_date",
                  "manager_unresolved")
    open_escs = session.exec(
        select(Escalation).where(
            Escalation.run_id == run.id, Escalation.status == "open"
        )
    ).all()
    for esc in open_escs:
        if esc.type in auto_types and esc.id not in still_open:
            esc.status = "resolved"
            esc.resolution_json = {"action": "auto", "value": "condition cleared on re-run"}
            esc.resolved_by = "agent"
            esc.resolved_at = datetime.now(timezone.utc)
            session.add(esc)
            audit(
                session, run.id, "agent", "auto_closed_escalation",
                "escalation", f"{esc.type}:{esc.entity_ref}",
                reason="condition no longer holds after re-run",
            )


def _set_gate_status(session: Session, run: MigrationRun) -> None:
    open_count = len(
        session.exec(
            select(Escalation).where(
                Escalation.run_id == run.id, Escalation.status == "open"
            )
        ).all()
    )
    run.status = "awaiting_review" if open_count else "ready_to_push"
    _touch(run)
    session.add(run)


def _recompute_stats(session: Session, run: MigrationRun) -> None:
    mappings = session.exec(
        select(FieldMapping).where(FieldMapping.run_id == run.id)
    ).all()
    records = session.exec(
        select(Record).where(Record.run_id == run.id)
    ).all()
    escalations = session.exec(
        select(Escalation).where(Escalation.run_id == run.id)
    ).all()
    auto_cleans = session.exec(
        select(AuditLog).where(
            AuditLog.run_id == run.id, AuditLog.action == "cleaned_value"
        )
    ).all()

    auto_mappings = sum(1 for m in mappings if m.status == "auto_applied")
    auto_clean_count = len(auto_cleans)
    total_escalations = len(escalations)
    open_esc = sum(1 for e in escalations if e.status == "open")
    human_resolved = sum(
        1 for e in escalations
        if e.status == "resolved" and e.resolved_by != "agent"
    )
    # STP: every autonomous win (a mapping applied with no human, or a value
    # auto-cleaned — target_schema.yaml's own enum_normalization comment
    # calls these "STP wins") against every decision point that existed,
    # including ones a human ultimately had to touch.
    auto_wins = auto_mappings + auto_clean_count
    total_decisions = auto_wins + total_escalations
    stp = round(auto_wins / total_decisions, 3) if total_decisions else 1.0

    run.stats_json = {
        "records": len(records),
        "valid": sum(1 for r in records if r.status == "valid"),
        "needs_review": sum(1 for r in records if r.status == "needs_review"),
        "pushed": sum(1 for r in records if r.status == "pushed"),
        "push_failed": sum(1 for r in records if r.status == "push_failed"),
        "auto_mappings": auto_mappings,
        "auto_cleans": auto_clean_count,
        "llm_mappings": sum(1 for m in mappings if m.method == "llm"
                            and m.status == "auto_applied"),
        "escalations_open": open_esc,
        "escalations_resolved": human_resolved,
        "stp_rate": stp,
    }
    session.add(run)
