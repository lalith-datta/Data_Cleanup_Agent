"""End-to-end demo-flow verification: full pipeline on sample data,
resolve every escalation, push, verify deterministic failure + retry +
rollback. Run with the backend up on :8000 (python scripts/e2e_demo.py)."""

import json
import time

import httpx

BASE = "http://localhost:8000"
DATA = "../data/source"


def main() -> None:
    run = httpx.post(f"{BASE}/api/runs", json={"name": "e2e"}).json()
    rid = run["id"]
    print(f"run {rid} created")

    with open(f"{DATA}/hr_export.csv", "rb") as a, \
         open(f"{DATA}/crm_export.csv", "rb") as b, \
         open(f"{DATA}/payroll_export.csv", "rb") as c:
        httpx.post(
            f"{BASE}/api/runs/{rid}/files",
            files=[("files", ("hr_export.csv", a)),
                   ("files", ("crm_export.csv", b)),
                   ("files", ("payroll_export.csv", c))],
        ).raise_for_status()
    print("files uploaded")

    httpx.post(f"{BASE}/api/runs/{rid}/start").raise_for_status()
    for _ in range(30):
        run = httpx.get(f"{BASE}/api/runs/{rid}").json()
        if run["status"] in ("awaiting_review", "ready_to_push", "failed"):
            break
        time.sleep(0.5)
    print("pipeline parked at:", run["status"])
    assert run["status"] == "awaiting_review"

    # consultant resolves everything the agent surfaced
    decisions = {
        "unmapped_column": ("reject", None),
        "ambiguous_mapping": ("reject", None),
        "value_conflict": ("approve", "__first__"),
        "validation_failure": ("correct", "__fix__"),
        "manager_unresolved": ("correct", "rahul.verma@acme.com"),
        "ambiguous_date": ("approve", "dd/mm"),
    }
    fixes = {"email": "fixed@acme.com", "date_of_birth": "1985-02-28",
             "employment_status": "active"}

    while True:
        open_escs = httpx.get(
            f"{BASE}/api/runs/{rid}/escalations?status=open"
        ).json()
        if not open_escs:
            break
        for esc in open_escs:
            action, value = decisions[esc["type"]]
            if value == "__first__":
                value = esc["options_json"][0]["value"]
            elif value == "__fix__":
                value = fixes.get(esc["context_json"]["field"], "active")
            # EmploymentType maps cleanly to employment_status
            if esc["entity_ref"].endswith("EmploymentType"):
                action, value = "correct", "employment_status"
            r = httpx.post(
                f"{BASE}/api/escalations/{esc['id']}/resolve",
                json={"action": action, "value": value,
                      "resolved_by": "consultant"},
            )
            assert r.status_code == 200, f"esc {esc['id']}: {r.text}"
        time.sleep(0.3)

    run = httpx.get(f"{BASE}/api/runs/{rid}").json()
    print("after review:", run["status"], "| stats:", json.dumps(run["stats_json"]))
    assert run["status"] == "ready_to_push"
    assert run["stats_json"]["escalations_open"] == 0

    # push — mock target deterministically fails gmail / missing department
    push = httpx.post(f"{BASE}/api/runs/{rid}/push").json()
    print("push:", push)
    assert push["pushed"] >= 1

    if push["failed"]:
        retry = httpx.post(f"{BASE}/api/runs/{rid}/push/retry").json()
        print("retry (still fails — deterministic rule):", retry)
        assert retry["still_failed"] >= 1

    rollback = httpx.post(f"{BASE}/api/runs/{rid}/rollback").json()
    print("rollback:", rollback)
    assert rollback["rolled_back"] >= 1

    audit = httpx.get(f"{BASE}/api/runs/{rid}/audit").json()
    print("audit entries:", len(audit))
    assert len(audit) > 20
    print("E2E OK")


if __name__ == "__main__":
    main()
