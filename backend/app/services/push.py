"""Push / retry / rollback (Epic 7.2–7.4).

Per-record push to the mock target with push_result rows, idempotent on each
run's configured primary key, retry capped by MAX_PUSH_ATTEMPTS, and rollback
that removes pushed records from the target. Everything is audited.
"""

from datetime import datetime, timezone

from sqlmodel import Session, select

from ..config import get_settings
from ..engines.schema_loader import get_run_schema
from ..models import MigrationRun, PushResult, Record
from .audit import audit
from .mock_target import get_mock_store
from .pipeline import _recompute_stats


def _pushable_records(session: Session, run_id: int) -> list[Record]:
    return session.exec(
        select(Record).where(
            Record.run_id == run_id, Record.status == "valid"
        )
    ).all()


def _attempt(session: Session, run: MigrationRun, rec: Record) -> PushResult:
    store = get_mock_store()
    payload = rec.merged_json
    schema = get_run_schema(run)
    status_code, body = store.create_record(
        payload, primary_key=schema.primary_key, run_id=run.id
    )
    attempt_no = (
        len(
            session.exec(
                select(PushResult).where(PushResult.record_id == rec.id)
            ).all()
        )
        + 1
    )
    ok = status_code == 200
    result = PushResult(
        run_id=run.id,
        record_id=rec.id,
        attempt=attempt_no,
        status="success" if ok else "failed",
        http_status=status_code,
        error="" if ok else str(body.get("error", body)),
        request_json=payload,
    )
    session.add(result)
    rec.status = "pushed" if ok else "push_failed"
    rec.updated_at = datetime.now(timezone.utc)
    session.add(rec)
    audit(
        session, run.id, "agent",
        "pushed_record" if ok else "push_failed",
        "record", rec.natural_key,
        after={"http_status": status_code, "attempt": attempt_no},
        reason="" if ok else str(body.get("error", body)),
    )
    return result


def push_run(session: Session, run: MigrationRun) -> dict:
    run.status = "pushing"
    run.updated_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()

    results = [
        _attempt(session, run, rec) for rec in _pushable_records(session, run.id)
    ]
    failed = [r for r in results if r.status == "failed"]
    run.status = "completed" if not failed else "pushing"  # stays until retried
    run.updated_at = datetime.now(timezone.utc)
    session.add(run)
    _recompute_stats(session, run)
    session.commit()
    return {
        "pushed": len(results) - len(failed),
        "failed": len(failed),
        "run_status": run.status,
    }


def retry_failed(session: Session, run: MigrationRun) -> dict:
    max_attempts = get_settings().max_push_attempts
    failed_records = session.exec(
        select(Record).where(
            Record.run_id == run.id, Record.status == "push_failed"
        )
    ).all()
    retried, exhausted = 0, 0
    for rec in failed_records:
        attempts = len(
            session.exec(
                select(PushResult).where(PushResult.record_id == rec.id)
            ).all()
        )
        if attempts >= max_attempts:
            exhausted += 1
            continue
        _attempt(session, run, rec)
        retried += 1
    remaining = session.exec(
        select(Record).where(
            Record.run_id == run.id, Record.status == "push_failed"
        )
    ).all()
    if not remaining:
        run.status = "completed"
        run.updated_at = datetime.now(timezone.utc)
        session.add(run)
    _recompute_stats(session, run)
    session.commit()
    return {"retried": retried, "exhausted": exhausted,
            "still_failed": len(remaining)}


def rollback_run(session: Session, run: MigrationRun) -> dict:
    store = get_mock_store()
    pushed = session.exec(
        select(Record).where(
            Record.run_id == run.id, Record.status == "pushed"
        )
    ).all()
    rolled_back = 0
    schema = get_run_schema(run)
    for rec in pushed:
        record_id = str(rec.merged_json.get(schema.primary_key) or "")
        if store.delete_record(record_id, schema.primary_key, run_id=run.id):
            rolled_back += 1
        rec.status = "rolled_back"
        rec.updated_at = datetime.now(timezone.utc)
        session.add(rec)
        audit(
            session, run.id, "agent", "rolled_back_record",
            "record", rec.natural_key,
            reason="rollback requested",
        )
    run.status = "rolled_back"
    run.updated_at = datetime.now(timezone.utc)
    session.add(run)
    _recompute_stats(session, run)
    session.commit()
    return {"rolled_back": rolled_back}
