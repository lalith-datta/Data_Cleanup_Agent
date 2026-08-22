"""Reset the demo to a clean slate and load the 3 sample files into a
ready-to-start run (Epic 13.1). Usage with backend stopped:

    python scripts/seed_demo.py

Then start the backend + frontend, open the run from the home screen, and
press Start. Deterministic: the sample data always yields the same
escalations and one push failure.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.db import create_db_and_tables, engine  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog, Escalation, FieldMapping, MigrationRun,
    PushResult, Record, SourceFile,
)
from app.storage import get_storage  # noqa: E402
from sqlmodel import Session, delete  # noqa: E402

DATA = BACKEND.parent / "data" / "source"
SAMPLES = ["hr_export.csv", "crm_export.csv", "payroll_export.csv"]


def main() -> None:
    create_db_and_tables()
    with Session(engine) as s:
        for model in (PushResult, AuditLog, Escalation, Record,
                      FieldMapping, SourceFile, MigrationRun):
            s.exec(delete(model))
        s.commit()

        run = MigrationRun(name="Demo — Acme Corp employee migration")
        s.add(run)
        s.commit()
        s.refresh(run)

        storage = get_storage()
        for fname in SAMPLES:
            data = (DATA / fname).read_bytes()
            path = storage.save_upload(run.id, fname, data)
            from app.engines.ingest import parse_file

            df = parse_file(path)
            s.add(
                SourceFile(
                    run_id=run.id,
                    filename=fname,
                    row_count=len(df),
                    columns_json=list(df.columns),
                    stored_path=path,
                )
            )
        s.commit()
        print(f"Seeded run #{run.id} with {len(SAMPLES)} sample files.")
        print("Start the backend, open the run, and press Start.")


if __name__ == "__main__":
    main()
