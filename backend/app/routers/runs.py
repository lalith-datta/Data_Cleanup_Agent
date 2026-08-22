"""Run lifecycle + file upload endpoints (PRD §10, Epic 1.1)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..engines.ingest import parse_file, profile_columns
from ..engines.schema_loader import (
    get_run_schema,
    load_schema_from_content,
    schema_to_dict,
)
from ..models import AuditLog, FieldMapping, MigrationRun, Record, SourceFile
from ..storage import get_storage

router = APIRouter(prefix="/api/runs", tags=["runs"])


class CreateRunBody(BaseModel):
    name: str


@router.post("")
def create_run(body: CreateRunBody, session: Session = Depends(get_session)):
    run = MigrationRun(name=body.name, status="created")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.get("")
def list_runs(session: Session = Depends(get_session)):
    return session.exec(
        select(MigrationRun).order_by(MigrationRun.id.desc())
    ).all()


@router.get("/{run_id}")
def get_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@router.post("/{run_id}/files")
async def upload_files(
    run_id: int,
    files: list[UploadFile],
    session: Session = Depends(get_session),
):
    run = session.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")

    storage = get_storage()
    saved: list[SourceFile] = []
    for f in files:
        data = await f.read()
        path = storage.save_upload(run_id, f.filename or "upload", data)
        df = parse_file(path)
        sf = SourceFile(
            run_id=run_id,
            filename=f.filename or "upload",
            row_count=len(df),
            columns_json=list(df.columns),
            stored_path=path,
        )
        session.add(sf)
        saved.append(sf)

    run.status = "ingesting"
    run.updated_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()
    for sf in saved:
        session.refresh(sf)
    return saved


@router.get("/{run_id}/files")
def list_files(run_id: int, session: Session = Depends(get_session)):
    return session.exec(
        select(SourceFile).where(SourceFile.run_id == run_id)
    ).all()


@router.get("/{run_id}/files/{file_id}/profile")
def file_profile(file_id: int, session: Session = Depends(get_session)):
    sf = session.get(SourceFile, file_id)
    if not sf:
        raise HTTPException(404, "file not found")
    df = parse_file(sf.stored_path)
    return {"file": sf.filename, "columns": profile_columns(df)}


@router.post("/{run_id}/start")
async def start_run(run_id: int, session: Session = Depends(get_session)):
    """Kick off the pipeline as an async background task (Epic 9.1). The run
    parks at awaiting_review when escalations are open; poll /activity for
    live progress."""
    run = session.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    from ..services.orchestrator import start_pipeline

    started = start_pipeline(run_id)
    if not started:
        raise HTTPException(409, "pipeline already running")
    return {"run_id": run_id, "started": True}


@router.get("/{run_id}/activity")
def activity_feed(
    run_id: int, since: int = 0, session: Session = Depends(get_session)
):
    """Human-readable stage events for the live view (Epic 9.3).
    `since` = last seen audit id, for incremental polling."""
    rows = session.exec(
        select(AuditLog).where(
            AuditLog.run_id == run_id,
            AuditLog.action.startswith("activity:"),
            AuditLog.id > since,
        ).order_by(AuditLog.id)
    ).all()
    return [
        {"id": r.id, "ts": r.ts, "stage": r.action.split(":", 1)[1],
         "message": r.reason}
        for r in rows
    ]


@router.get("/{run_id}/records")
def list_records(
    run_id: int, status: str = "", session: Session = Depends(get_session)
):
    q = select(Record).where(Record.run_id == run_id)
    if status:
        q = q.where(Record.status == status)
    return session.exec(q.order_by(Record.id)).all()


@router.post("/{run_id}/push")
def push(run_id: int, session: Session = Depends(get_session)):
    run = session.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if run.status != "ready_to_push":
        raise HTTPException(
            409, f"run must be ready_to_push (currently {run.status})"
        )
    from ..services.push import push_run

    return push_run(session, run)


@router.post("/{run_id}/push/retry")
def push_retry(run_id: int, session: Session = Depends(get_session)):
    run = session.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if run.status not in ("pushing", "completed"):
        raise HTTPException(
            409, f"run has nothing pushed yet (currently {run.status})"
        )
    from ..services.push import retry_failed

    return retry_failed(session, run)


@router.post("/{run_id}/rollback")
def rollback(run_id: int, session: Session = Depends(get_session)):
    run = session.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if run.status not in ("pushing", "completed"):
        raise HTTPException(
            409, f"run has nothing pushed to roll back (currently {run.status})"
        )
    from ..services.push import rollback_run

    return rollback_run(session, run)


@router.get("/{run_id}/audit")
def audit_log(run_id: int, session: Session = Depends(get_session)):
    return session.exec(
        select(AuditLog)
        .where(AuditLog.run_id == run_id)
        .order_by(AuditLog.id)
    ).all()


@router.get("/{run_id}/mappings")
def list_mappings(run_id: int, session: Session = Depends(get_session)):
    return session.exec(
        select(FieldMapping).where(FieldMapping.run_id == run_id)
    ).all()


# -------------------------------------------------------- schema management
@router.post("/{run_id}/schema")
async def upload_schema(
    run_id: int,
    file: UploadFile,
    session: Session = Depends(get_session),
):
    """Upload a custom target schema (YAML or JSON) for this run.
    The parser is lenient: a bare list of field names, a dict with just
    'fields', or a full spec are all accepted."""
    run = session.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if run.status not in ("created", "ingesting"):
        raise HTTPException(
            409, f"cannot change schema after pipeline has started (status: {run.status})"
        )

    filename = (file.filename or "").lower()
    if filename.endswith(".json"):
        fmt = "json"
    elif filename.endswith((".yaml", ".yml")):
        fmt = "yaml"
    else:
        raise HTTPException(
            422, "Unsupported file type. Upload a .yaml, .yml, or .json file."
        )

    content = (await file.read()).decode("utf-8")
    try:
        schema = load_schema_from_content(content, fmt)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    # Store the raw parsed dict (not the Pydantic model) so we can
    # re-parse leniently on every access — keeps the column small.
    run.custom_schema_json = schema_to_dict(schema)
    run.updated_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()
    session.refresh(run)

    return {
        "message": "Schema uploaded successfully",
        "schema": _schema_preview(schema),
    }


@router.get("/{run_id}/schema")
def get_schema(run_id: int, session: Session = Depends(get_session)):
    """Return the effective schema for this run (custom if uploaded, else
    the default). Includes a preview of all parsed fields."""
    run = session.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    schema = get_run_schema(run)
    return {
        "custom": run.custom_schema_json is not None,
        "schema": _schema_preview(schema),
    }


@router.delete("/{run_id}/schema")
def delete_schema(run_id: int, session: Session = Depends(get_session)):
    """Clear the custom schema, reverting to the default."""
    run = session.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if run.status not in ("created", "ingesting"):
        raise HTTPException(
            409, f"cannot change schema after pipeline has started (status: {run.status})"
        )
    run.custom_schema_json = None
    run.updated_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()
    return {"message": "Custom schema removed, using default."}


def _schema_preview(schema) -> dict:
    """Build a human-friendly preview of a parsed schema."""
    return {
        "entity": schema.entity,
        "primary_key": schema.primary_key,
        "match_keys": schema.match_keys,
        "field_count": len(schema.fields),
        "fields": [
            {
                "name": f.name,
                "type": f.type,
                "required": f.required,
                "aliases": f.aliases,
            }
            for f in schema.fields.values()
        ],
    }
