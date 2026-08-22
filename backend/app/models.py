"""Data model per docs/PRD.md §6 (SQLite default, Postgres-ready)."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MigrationRun(SQLModel, table=True):
    __tablename__ = "migration_run"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    status: str = "created"
    # created | ingesting | mapping | reconciling | cleaning | validating |
    # awaiting_review | ready_to_push | pushing | completed | failed | rolled_back
    config_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    stats_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # User-uploaded target schema (raw parsed dict). None = use default file.
    custom_schema_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SourceFile(SQLModel, table=True):
    __tablename__ = "source_file"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="migration_run.id", index=True)
    filename: str
    entity: str = "employee"
    row_count: int = 0
    columns_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    stored_path: str = ""
    uploaded_at: datetime = Field(default_factory=utcnow)


class FieldMapping(SQLModel, table=True):
    __tablename__ = "field_mapping"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="migration_run.id", index=True)
    source_file_id: int = Field(foreign_key="source_file.id")
    source_column: str
    target_field: Optional[str] = None
    method: str = "fuzzy"  # alias | fuzzy | llm | manual
    confidence: float = 0.0
    status: str = "auto_applied"  # auto_applied | escalated | resolved | rejected
    rationale: str = ""
    candidates_json: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    created_at: datetime = Field(default_factory=utcnow)


class Record(SQLModel, table=True):
    __tablename__ = "record"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="migration_run.id", index=True)
    natural_key: str = ""  # reconciled key (email primary, id fallback)
    merged_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source_refs_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )  # field -> {"file": filename, "raw": original_value}
    status: str = "clean"
    # clean | needs_review | valid | invalid | pushed | push_failed | rolled_back
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Escalation(SQLModel, table=True):
    __tablename__ = "escalation"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="migration_run.id", index=True)
    type: str = ""
    # ambiguous_mapping | value_conflict | ambiguous_date |
    # validation_failure | unmapped_column | manager_unresolved
    entity_ref: str = ""  # record natural key or source column name
    context_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    options_json: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    confidence: float = 0.0
    status: str = "open"  # open | resolved | rejected
    resolution_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="migration_run.id", index=True)
    ts: datetime = Field(default_factory=utcnow)
    actor: str = "agent"  # agent | human
    action: str = ""
    target_type: str = ""
    target_id: str = ""
    before_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    after_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    reason: str = ""


class PushResult(SQLModel, table=True):
    __tablename__ = "push_result"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="migration_run.id", index=True)
    record_id: int = Field(foreign_key="record.id")
    attempt: int = 1
    status: str = "success"  # success | failed
    http_status: int = 0
    error: str = ""
    request_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
