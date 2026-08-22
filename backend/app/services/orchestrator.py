"""Orchestrator (Epic 9.1): runs the pipeline as an async background task.

Important: the background task opens its OWN DB session — the request
session that triggered it closes when the response returns. Stage
transitions are written to the activity feed as they happen so the live
view can poll them (Epic 9.3).
"""

import asyncio

from sqlmodel import Session

from ..db import engine
from ..models import MigrationRun
from .activity import log_activity
from .pipeline import run_downstream_stages, run_mapping_stage

# run_id -> asyncio.Task, so we can inspect/guard against double-starts
_running: dict[int, asyncio.Task] = {}


async def _execute(run_id: int) -> None:
    with Session(engine) as session:
        run = session.get(MigrationRun, run_id)
        if not run:
            return
        try:
            log_activity(session, run_id, "ingesting",
                         "Reading your files and profiling the columns.")
            log_activity(session, run_id, "mapping",
                         "Working out which columns match which fields.")
            await run_mapping_stage(session, run)

            log_activity(session, run_id, "reconciling",
                         "Matching the same people across files, then cleaning "
                         "and checking every value.")
            run_downstream_stages(session, run)

            session.refresh(run)
            if run.status == "awaiting_review":
                open_n = run.stats_json.get("escalations_open", 0)
                log_activity(
                    session, run_id, "awaiting_review",
                    f"Done with the automatic work. {open_n} thing(s) need "
                    "your input before we can send.",
                )
            else:
                log_activity(session, run_id, run.status,
                             "Everything was handled automatically — ready to "
                             "send to the new system.")
        except Exception:  # never leave a run hung
            import traceback

            traceback.print_exc()  # full detail for the developer console
            run.status = "failed"
            session.add(run)
            log_activity(
                session, run_id, "failed",
                "Something went wrong while the agent was working, and this "
                "run has stopped. Check the server console, or start a new "
                "run.",
            )
            session.commit()
        finally:
            _running.pop(run_id, None)


def start_pipeline(run_id: int) -> bool:
    """Kick off the background pipeline. Returns False if already running."""
    if run_id in _running and not _running[run_id].done():
        return False
    _running[run_id] = asyncio.create_task(_execute(run_id))
    return True
