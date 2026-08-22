"""Escalation engine (Epic 6): the supervision core.

Escalations are deduped (same run+type+entity_ref stays a single open item).
Each resolution applies its effect, audits it, and re-triggers the minimal
affected downstream stage (PRD §6/§9). When the queue empties, the run
advances to ready_to_push.
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from ..engines.schema_loader import get_run_schema
from ..engines.validate import validate_record
from ..models import Escalation, FieldMapping, MigrationRun, Record, SourceFile
from .audit import audit


def find_open(
    session: Session, run_id: int, type_: str, entity_ref: str
) -> Escalation | None:
    return session.exec(
        select(Escalation).where(
            Escalation.run_id == run_id,
            Escalation.type == type_,
            Escalation.entity_ref == entity_ref,
            Escalation.status == "open",
        )
    ).first()


def raise_escalation(
    session: Session,
    run_id: int,
    type_: str,
    entity_ref: str,
    context: dict,
    options: list[dict],
    confidence: float = 0.0,
) -> Escalation:
    existing = find_open(session, run_id, type_, entity_ref)
    if existing:
        return existing
    esc = Escalation(
        run_id=run_id,
        type=type_,
        entity_ref=entity_ref,
        context_json=context,
        options_json=options,
        confidence=confidence,
    )
    session.add(esc)
    session.flush()
    audit(
        session, run_id, "agent", "escalated",
        "escalation", f"{type_}:{entity_ref}",
        after={"context": context},
        reason=f"low-confidence {type_} requires human judgment",
    )
    return esc


def resolve_escalation(
    session: Session, esc: Escalation, action: str, value: str | None,
    resolved_by: str = "consultant",
) -> Escalation:
    """action: approve | correct | reject. `value` carries the human's choice."""
    run = session.get(MigrationRun, esc.run_id)
    assert run is not None

    # Mark resolved FIRST and flush: resolution handlers re-validate records
    # and check for open escalations — the escalation being resolved must not
    # count itself as still-open, or the record never leaves needs_review.
    esc.status = "rejected" if action == "reject" else "resolved"
    esc.resolution_json = {"action": action, "value": value}
    esc.resolved_by = resolved_by
    esc.resolved_at = datetime.now(timezone.utc)
    session.add(esc)
    session.flush()

    if esc.type in ("ambiguous_mapping", "unmapped_column"):
        _apply_mapping_resolution(session, esc, action, value)
        # mapping changed -> re-merge everything downstream
        from .pipeline import run_downstream_stages

        run_downstream_stages(session, run)

    elif esc.type == "value_conflict":
        _apply_value_conflict(session, esc, value)
        _reclean_revalidate_record(
            session, run, esc.context_json.get("record", esc.entity_ref)
        )

    elif esc.type == "ambiguous_date":
        _apply_date_format(session, run, esc, value)
        from .pipeline import run_downstream_stages

        run_downstream_stages(session, run)  # re-clean field-wide + re-validate

    elif esc.type == "validation_failure":
        _apply_validation_fix(session, esc, action, value)
        _revalidate_record(session, run, esc.entity_ref.rsplit(":", 1)[0])

    elif esc.type == "manager_unresolved":
        _apply_manager(session, esc, action, value)
        _revalidate_record(session, run, esc.entity_ref)

    audit(
        session, esc.run_id, "human", f"resolved_{esc.type}",
        "escalation", esc.entity_ref,
        before={"context": esc.context_json},
        after={"action": action, "value": value},
        reason=f"human decision by {resolved_by}",
    )

    from .pipeline import _recompute_stats, _set_gate_status

    _recompute_stats(session, run)
    _set_gate_status(session, run)
    session.commit()
    session.refresh(esc)
    return esc


# ------------------------------------------------------- resolution handlers
def _apply_mapping_resolution(
    session: Session, esc: Escalation, action: str, value: str | None
) -> None:
    filename, column = esc.entity_ref.split(":", 1)
    sf = session.exec(
        select(SourceFile).where(
            SourceFile.run_id == esc.run_id, SourceFile.filename == filename
        )
    ).first()
    if not sf:
        return
    fm = session.exec(
        select(FieldMapping).where(
            FieldMapping.source_file_id == sf.id,
            FieldMapping.source_column == column,
        )
    ).first()
    if not fm:
        return
    if action == "reject" or value in (None, "", "__drop__"):
        fm.status = "rejected"  # column dropped — surfaced, never silent
        fm.target_field = None
    else:
        # §9 only allows "pick target · ignore column" for this type — a
        # free-typed value must still name a real schema field, or a typo'd
        # correction would silently corrupt the mapping at confidence 1.0.
        run = session.get(MigrationRun, esc.run_id)
        schema = get_run_schema(run) if run else None
        if schema and value not in schema.field_names():
            raise HTTPException(
                422,
                f"'{value}' is not a target schema field — pick one of the "
                "listed candidates or drop the column",
            )
        fm.target_field = value
        fm.method = "manual"
        fm.confidence = 1.0
        fm.status = "resolved"
    session.add(fm)


def _store_override(
    session: Session, run: MigrationRun, natural_key: str, field: str, value: str | None
) -> None:
    """Manual human edits must survive later re-runs (mapping/date
    resolutions rebuild records from source). Persist them on the run and
    re-apply during every rebuild."""
    config = dict(run.config_json)
    overrides = dict(config.get("manual_overrides", {}))
    record_overrides = dict(overrides.get(natural_key, {}))
    record_overrides[field] = value
    overrides[natural_key] = record_overrides
    config["manual_overrides"] = overrides
    run.config_json = config
    session.add(run)


def _apply_value_conflict(
    session: Session, esc: Escalation, value: str | None
) -> None:
    field_name = esc.context_json.get("field")
    natural_key = esc.context_json.get("record", "")
    run = session.get(MigrationRun, esc.run_id)
    rec = _record_by_key(session, esc.run_id, natural_key)
    if rec and field_name and value:
        before = rec.merged_json.get(field_name)
        rec.merged_json = {**rec.merged_json, field_name: value}
        rec.source_refs_json = {
            **rec.source_refs_json,
            field_name: {"file": "human", "raw": value},
        }
        session.add(rec)
        if run:
            _store_override(session, run, natural_key, field_name, value)
        # resolve_escalation() writes the generic "resolved_value_conflict"
        # audit entry for every type, including this one — don't double it.


def _apply_date_format(
    session: Session, run: MigrationRun, esc: Escalation, value: str | None
) -> None:
    if not value:
        return
    config = dict(run.config_json)
    forced = dict(config.get("forced_formats", {}))
    forced[esc.entity_ref] = value  # applied field-wide on re-clean
    config["forced_formats"] = forced
    run.config_json = config
    session.add(run)


def _apply_validation_fix(
    session: Session, esc: Escalation, action: str, value: str | None
) -> None:
    # entity_ref is "{natural_key}:{field}" and natural_key itself contains
    # a colon ("email:x@y.com") — split from the RIGHT
    key, field_name = esc.entity_ref.rsplit(":", 1)
    rec = _record_by_key(session, esc.run_id, key)
    if not rec:
        return
    if action == "reject":
        rec.status = "invalid"
        session.add(rec)
        return
    if value is not None:
        rec.merged_json = {**rec.merged_json, field_name: value}
        session.add(rec)
        run = session.get(MigrationRun, esc.run_id)
        if run:
            _store_override(session, run, key, field_name, value)


def _apply_manager(
    session: Session, esc: Escalation, action: str, value: str | None
) -> None:
    rec = _record_by_key(session, esc.run_id, esc.entity_ref)
    if not rec:
        return
    rec.merged_json = {
        **rec.merged_json,
        "manager_email": value if value else None,
    }
    session.add(rec)
    run = session.get(MigrationRun, esc.run_id)
    if run:
        _store_override(session, run, esc.entity_ref, "manager_email", value)


# --------------------------------------------------------------- re-triggers
def _reclean_revalidate_record(
    session: Session, run: MigrationRun, natural_key: str
) -> None:
    from ..engines.clean import clean_record

    schema = get_run_schema(run)
    rec = _record_by_key(session, run.id, natural_key)
    if not rec:
        return
    forced = run.config_json.get("forced_formats", {})
    cr = clean_record(rec.merged_json, rec.source_refs_json, schema, forced)
    rec.merged_json = cr.cleaned
    _finish_validation(session, run, rec, schema)


def _revalidate_record(
    session: Session, run: MigrationRun, natural_key: str
) -> None:
    schema = get_run_schema(run)
    rec = _record_by_key(session, run.id, natural_key)
    if rec:
        _finish_validation(session, run, rec, schema)


def _finish_validation(
    session: Session, run: MigrationRun, rec: Record, schema
) -> None:
    if rec.status == "invalid":
        return
    errors = validate_record(rec.merged_json, schema)
    still_open = session.exec(
        select(Escalation).where(
            Escalation.run_id == run.id,
            Escalation.status == "open",
            Escalation.entity_ref.contains(rec.natural_key),
        )
    ).all()
    rec.status = "needs_review" if (errors or still_open) else "valid"
    rec.updated_at = datetime.now(timezone.utc)
    session.add(rec)


def _record_by_key(session: Session, run_id: int, natural_key: str) -> Record | None:
    return session.exec(
        select(Record).where(
            Record.run_id == run_id, Record.natural_key == natural_key
        )
    ).first()
