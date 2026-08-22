"""Mock target HTTP surface (Epic 7.1) — what a real client system would
expose. The push client uses the store directly (same process); these routes
exist for demo realism and manual inspection."""

from fastapi import APIRouter

from ..services.mock_target import get_mock_store

router = APIRouter(prefix="/api/mock-target", tags=["mock-target"])


@router.post("/employees")
def create_employee(payload: dict):
    status, body = get_mock_store().create_employee(payload)
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status, content=body)


@router.delete("/employees/{employee_id}")
def delete_employee(employee_id: str):
    deleted = get_mock_store().delete_employee(employee_id)
    return {"deleted": deleted}


@router.get("/employees")
def list_employees():
    return get_mock_store().list_employees()
