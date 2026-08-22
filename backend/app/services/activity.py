"""Activity feed (Epic 9.3): lightweight, human-readable stage events the
live view polls. Distinct from the audit log (which is the complete,
formal record); the feed is the narrated storyline."""

from datetime import datetime, timezone

from sqlmodel import Session

from ..models import AuditLog


def log_activity(session: Session, run_id: int, stage: str, message: str) -> None:
    session.add(
        AuditLog(
            run_id=run_id,
            actor="agent",
            action=f"activity:{stage}",
            target_type="run",
            target_id=str(run_id),
            reason=message,
            ts=datetime.now(timezone.utc),
        )
    )
    session.commit()
