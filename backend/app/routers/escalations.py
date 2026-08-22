"""Escalation endpoints (PRD §10, Epic 6.1)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Escalation
from ..services.escalations import resolve_escalation

router = APIRouter(tags=["escalations"])


class ResolveBody(BaseModel):
    action: str  # approve | correct | reject
    value: str | None = None
    resolved_by: str = "consultant"


@router.get("/api/runs/{run_id}/escalations")
def list_escalations(
    run_id: int, status: str = "open", session: Session = Depends(get_session)
):
    q = select(Escalation).where(Escalation.run_id == run_id)
    if status != "all":
        q = q.where(Escalation.status == status)
    return session.exec(q.order_by(Escalation.created_at)).all()


@router.post("/api/escalations/{escalation_id}/resolve")
def resolve(
    escalation_id: int, body: ResolveBody, session: Session = Depends(get_session)
):
    esc = session.get(Escalation, escalation_id)
    if not esc:
        raise HTTPException(404, "escalation not found")
    if esc.status != "open":
        raise HTTPException(409, "escalation already resolved")
    if body.action not in ("approve", "correct", "reject"):
        raise HTTPException(422, "action must be approve | correct | reject")
    return resolve_escalation(session, esc, body.action, body.value, body.resolved_by)
