"""Mock target system (Epic 7.1): simulates the client's new platform.

Deterministic failure rules (demo-safe, PRD §10): a record fails with 422
when its email domain is gmail.com OR department is missing — guaranteeing
a retryable failure on camera without any randomness. A missing employee_id
also fails (a record should never reach push without one, since it's a
required schema field caught at Validate — this is a defensive backstop,
not a third demo scenario).

The store is in-memory and keyed on employee_id, so pushes are naturally
idempotent: re-pushing the same employee updates instead of duplicating.
"""

from typing import Any


class MockTargetStore:
    def __init__(self) -> None:
        self._employees: dict[str, dict[str, Any]] = {}
        # Which run most recently pushed each employee — so an older run's
        # rollback can never delete a newer run's live record (the store is
        # process-wide and shared across runs; that's the only thing that
        # makes idempotent-by-employee_id upsert safe across reruns).
        self._owner_run: dict[str, int] = {}

    def reset(self) -> None:
        self._employees.clear()
        self._owner_run.clear()

    def create_employee(
        self, payload: dict[str, Any], run_id: int | None = None
    ) -> tuple[int, dict]:
        """Returns (http_status, body). 422 on deterministic failure rule."""
        email = str(payload.get("email") or "").strip().lower()
        department = payload.get("department")
        employee_id = str(payload.get("employee_id") or "")

        if not employee_id:
            return 422, {"error": "employee_id required"}
        if email.endswith("@gmail.com"):
            return 422, {"error": "personal email domains are not accepted"}
        if not department:
            return 422, {"error": "department is mandatory in target system"}

        self._employees[employee_id] = dict(payload)  # upsert = idempotent
        if run_id is not None:
            self._owner_run[employee_id] = run_id
        return 200, {"employee_id": employee_id, "created": True}

    def delete_employee(self, employee_id: str, run_id: int | None = None) -> bool:
        """False (no-op) if `run_id` isn't the run that currently owns this
        employee — e.g. a different, newer run already re-pushed it."""
        if run_id is not None and self._owner_run.get(employee_id) != run_id:
            return False
        removed = self._employees.pop(employee_id, None) is not None
        self._owner_run.pop(employee_id, None)
        return removed

    def list_employees(self) -> list[dict[str, Any]]:
        return list(self._employees.values())


_store = MockTargetStore()


def get_mock_store() -> MockTargetStore:
    return _store
