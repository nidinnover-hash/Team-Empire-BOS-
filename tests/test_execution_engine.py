from app.core.security import create_access_token


def _auth_headers(user_id: int, email: str, role: str, org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def test_execution_runs_and_succeeds(client):
    requester = _auth_headers(3, "manager@org.com", "MANAGER", 1)
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "assign_leads", "payload_json": {"count": 5}},
        headers=requester,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    approver = _auth_headers(1, "ceo@org.com", "CEO", 1)
    approve = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "YES EXECUTE"},
        headers=approver,
    )
    assert approve.status_code == 200

    executions = await client.get("/api/v1/executions", headers=approver)
    assert executions.status_code == 200
    assert any(
        e["approval_id"] == approval_id and e["status"] == "succeeded"
        for e in executions.json()
    )


async def test_execution_failure_is_recorded(client):
    requester = _auth_headers(3, "manager@org.com", "MANAGER", 1)
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "spend", "payload_json": {"force_fail": True, "amount": 10}},
        headers=requester,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    approver = _auth_headers(1, "ceo@org.com", "CEO", 1)
    approve = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "YES EXECUTE"},
        headers=approver,
    )
    assert approve.status_code == 200

    executions = await client.get("/api/v1/executions", headers=approver)
    assert any(
        e["approval_id"] == approval_id and e["status"] == "failed"
        for e in executions.json()
    )


async def test_approval_without_yes_execute_does_not_run_execution(client):
    requester = _auth_headers(3, "manager@org.com", "MANAGER", 1)
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "archive_note", "payload_json": {"note_id": 1}},
        headers=requester,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    approver = _auth_headers(1, "ceo@org.com", "CEO", 1)
    approve = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "Approved"},
        headers=approver,
    )
    assert approve.status_code == 200

    executions = await client.get("/api/v1/executions", headers=approver)
    assert not any(e["approval_id"] == approval_id for e in executions.json())


async def test_calendar_digest_execution_output(client):
    requester = _auth_headers(3, "manager@org.com", "MANAGER", 1)
    req = await client.post(
        "/api/v1/approvals/request",
        json={
            "organization_id": 1,
            "approval_type": "fetch_calendar_digest",
            "payload_json": {
                "date": "2026-02-21",
                "events": [
                    {
                        "title": "Standup",
                        "start": "2026-02-21T09:00:00+00:00",
                        "end": "2026-02-21T09:30:00+00:00",
                    },
                    {
                        "title": "Client Call",
                        "start": "2026-02-21T10:00:00+00:00",
                        "end": "2026-02-21T10:45:00+00:00",
                    },
                ],
            },
        },
        headers=requester,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    approver = _auth_headers(1, "ceo@org.com", "CEO", 1)
    approve = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "YES EXECUTE"},
        headers=approver,
    )
    assert approve.status_code == 200

    executions = await client.get("/api/v1/executions", headers=approver)
    matched = [e for e in executions.json() if e["approval_id"] == approval_id]
    assert matched
    execution = matched[0]
    assert execution["status"] == "succeeded"
    assert execution["output_json"]["total_events"] == 2
    assert "events on 2026-02-21" in execution["output_json"]["summary"]
