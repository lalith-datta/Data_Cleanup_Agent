"""Mock target system (Epic 7.1): simulates the client's new platform.

Deterministic failure rule (demo-safe, PRD §10): a record fails with 422
when it's missing a value the DESTINATION system requires beyond this run's
own schema (TargetSchema.target_system_rules) — e.g. the employee schema
declares department required and gmail.com blocked; a custom schema can
declare its own equivalents, or none at all.

The store is in-memory and keyed on each schema's primary-key name and value,
so pushes are naturally idempotent without collisions between entity types.
"""

from typing import Any


class MockTargetStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], dict[str, Any]] = {}
        # Which run most recently pushed each record — so an older run's
        # rollback can never delete a newer run's live record (the store is
        # process-wide and shared across runs; that's the only thing that
        # makes idempotent upserts safe across reruns).
        self._owner_run: dict[tuple[str, str], int] = {}

    def reset(self) -> None:
        self._records.clear()
        self._owner_run.clear()

    def create_record(
        self,
        payload: dict[str, Any],
        primary_key: str,
        run_id: int | None = None,
        required_fields: list[str] | None = None,
        blocked_email_domains: list[str] | None = None,
    ) -> tuple[int, dict]:
        """Upsert one record using the schema's primary key.

        `required_fields`/`blocked_email_domains` are the destination
        system's OWN extra rules (TargetSchema.target_system_rules) — not
        this schema's required-field validation, which every `valid`
        record has already satisfied by the time it reaches push. No rules
        declared means nothing extra can fail here, which is a legitimate
        outcome for a schema that doesn't declare any.
        """
        email = str(payload.get("email") or "").strip().lower()
        record_id = str(payload.get(primary_key) or "").strip()
        storage_key = (primary_key, record_id)

        if not record_id:
            return 422, {"error": f"{primary_key} required"}
        for domain in blocked_email_domains or []:
            if email.endswith(f"@{domain.strip().lower()}"):
                return 422, {"error": f"{domain} email domains are not accepted"}
        for req_field in required_fields or []:
            if not payload.get(req_field):
                return 422, {"error": f"{req_field} is mandatory in target system"}

        self._records[storage_key] = dict(payload)  # upsert = idempotent
        if run_id is not None:
            self._owner_run[storage_key] = run_id
        return 200, {primary_key: record_id, "created": True}

    def create_employee(
        self, payload: dict[str, Any], run_id: int | None = None
    ) -> tuple[int, dict]:
        """Backwards-compatible employee endpoint for manual demo calls —
        the historic employee rules, explicit here rather than special-cased
        inside create_record."""
        return self.create_record(
            payload,
            "employee_id",
            run_id,
            required_fields=["department"],
            blocked_email_domains=["gmail.com"],
        )

    def delete_record(
        self, record_id: str, primary_key: str, run_id: int | None = None
    ) -> bool:
        """False (no-op) if `run_id` isn't the run that currently owns this
        record — e.g. a different, newer run already re-pushed it."""
        storage_key = (primary_key, record_id)
        if run_id is not None and self._owner_run.get(storage_key) != run_id:
            return False
        removed = self._records.pop(storage_key, None) is not None
        self._owner_run.pop(storage_key, None)
        return removed

    def delete_employee(self, employee_id: str, run_id: int | None = None) -> bool:
        return self.delete_record(employee_id, "employee_id", run_id)

    def list_employees(self) -> list[dict[str, Any]]:
        return list(self._records.values())


_store = MockTargetStore()


def get_mock_store() -> MockTargetStore:
    return _store
