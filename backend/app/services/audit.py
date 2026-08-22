"""Audit trail (Epic 8.1): one writer used by every stage and every human
action. Complete, inspectable record — what changed, why, by whom."""

from typing import Any

from sqlmodel import Session

from ..models import AuditLog


def audit(
    session: Session,
    run_id: int,
    actor: str,  # agent | human
    action: str,
    target_type: str = "",
    target_id: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
) -> None:
    session.add(
        AuditLog(
            run_id=run_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            before_json=before or {},
            after_json=after or {},
            reason=reason,
        )
    )
    # Flush (not commit) so a DB-level failure on this write surfaces right
    # here rather than silently at whatever unrelated commit happens later.
    session.flush()
