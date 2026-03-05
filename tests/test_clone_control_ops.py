from datetime import date

from tests.conftest import _make_auth_headers


async def test_clone_identity_profile_feedback_training_flow(client):
    headers = _make_auth_headers()
    emp = await client.post(
        "/api/v1/ops/employees",
        json={"name": "Flow User", "email": "flow@org.com", "job_title": "Developer"},
        headers=headers,
    )
    assert emp.status_code == 201
    employee_id = emp.json()["id"]

    identity = await client.post(
        "/api/v1/ops/clones/identity-map",
        json={"employee_id": employee_id, "work_email": "flow@org.com", "github_login": "flowdev"},
        headers=headers,
    )
    assert identity.status_code == 200

    profile = await client.post(
        "/api/v1/ops/clones/profile",
        json={
            "employee_id": employee_id,
            "strengths": ["debugging", "delivery"],
            "weak_zones": ["documentation"],
            "preferred_task_types": ["tech", "backend"],
        },
        headers=headers,
    )
    assert profile.status_code == 200
    assert "strengths" in profile.json()

    feedback = await client.post(
        "/api/v1/ops/clones/feedback",
        json={"employee_id": employee_id, "source_type": "task", "source_id": 1001, "outcome_score": 0.9},
        headers=headers,
    )
    assert feedback.status_code == 200
    assert feedback.json()["ok"] is True

    week = date(2026, 2, 23).isoformat()
    trained = await client.post(f"/api/v1/ops/clones/train?week_start={week}", headers=headers)
    assert trained.status_code == 200

    generated = await client.post(f"/api/v1/ops/clones/training-plan/generate?week_start={week}", headers=headers)
    assert generated.status_code == 200
    assert generated.json()["ok"] is True

    plans = await client.get(f"/api/v1/ops/clones/training-plan?week_start={week}", headers=headers)
    assert plans.status_code == 200
    if plans.json():
        plan_id = plans.json()[0]["id"]
        updated = await client.patch(
            f"/api/v1/ops/clones/training-plan/{plan_id}",
            json={"status": "DONE"},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "DONE"
