r"""Prove the Postgres/Supabase path end-to-end at the DB layer.

Run this BEFORE deploying to confirm the driver, connection, SSL, table
creation, and a full CRUD round-trip all work against your real database.

Usage (PowerShell):
    $env:DATABASE_URL = "postgresql+psycopg://postgres.REF:PWD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require"
    .\.venv\Scripts\python.exe scripts\verify_postgres.py

Usage (bash):
    export DATABASE_URL="postgresql+psycopg://...?sslmode=require"
    python scripts/verify_postgres.py

It creates the schema, writes + reads + deletes a throwaway run, and cleans
up after itself. Safe to run against the Supabase project you'll deploy to.
"""

import os
import sys

url = os.environ.get("DATABASE_URL", "")
if not url:
    sys.exit("DATABASE_URL is not set. Set it to your Supabase connection "
             "string (with +psycopg and ?sslmode=require) and re-run.")
if url.startswith("sqlite"):
    sys.exit("DATABASE_URL points at SQLite. Set it to your Postgres/Supabase "
             "URL to verify the deployment path.")

# Import AFTER the env var is set so the app's engine binds to this URL.
from sqlmodel import Session, select  # noqa: E402

from app.db import create_db_and_tables, engine  # noqa: E402
from app.models import MigrationRun, SourceFile  # noqa: E402


def main() -> None:
    print(f"→ Driver:  {engine.dialect.name}+{engine.dialect.driver}")
    print(f"→ Target:  {engine.url.host}")

    print("→ Creating tables (idempotent)…")
    create_db_and_tables()

    print("→ Write + read + delete round-trip…")
    with Session(engine) as s:
        run = MigrationRun(name="__verify__ throwaway")
        s.add(run)
        s.commit()
        s.refresh(run)

        s.add(SourceFile(run_id=run.id, filename="probe.csv",
                         row_count=1, columns_json=["a", "b"]))
        s.commit()

        got = s.exec(
            select(MigrationRun).where(MigrationRun.id == run.id)
        ).one()
        files = s.exec(
            select(SourceFile).where(SourceFile.run_id == run.id)
        ).all()
        assert got.name == "__verify__ throwaway"
        assert len(files) == 1 and files[0].columns_json == ["a", "b"]

        # clean up
        for f in files:
            s.delete(f)
        s.delete(got)
        s.commit()

    print("\n✅ Postgres path verified — driver, SSL, table creation, and JSON "
          "columns all work. You're clear to deploy.")


if __name__ == "__main__":
    main()
