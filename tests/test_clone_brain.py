from datetime import date

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.ops_metrics import CodeMetricWeekly, CommsMetricWeekly, TaskMetricWeekly


async def _insert_weekly_metrics(*, org_id: int, employee_id: int, week_start: date) -> None:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        session.add(
            TaskMetricWeekly(
                organization_id=org_id,
                employee_id=employee_id,
                week_start_date=week_start,
                tasks_assigned=8,
                tasks_completed=7,
                on_time_rate=0.9,
                avg_cycle_time_hours=12.0,
                reopen_count=0,
            )
        )
        session.add(
            CodeMetricWeekly(
                organization_id=org_id,
                employee_id=employee_id,
                week_start_date=week_start,
                commits=12,
                prs_opened=5,
                prs_merged=4,
                reviews_done=6,
                issue_links=4,
                files_touched_count=45,
            )
        )
        session.add(
            CommsMetricWeekly(
                organization_id=org_id,
                employee_id=employee_id,
                week_start_date=week_start,
                emails_sent=20,
                emails_replied=18,
                median_reply_time_minutes=60.0,
                escalation_count=1,
            )
        )
        await session.commit()
    finally:
        await agen.aclose()


async def test_clone_brain_training_and_dispatch(client):
    week_start = date(2026, 2, 23)

    created = await client.post(
        "/api/v1/ops/employees",
        json={"name": "Clone Dev", "email": "clonedev@org.com", "job_title": "Developer"},
    )
    assert created.status_code == 201
    employee_id = created.json()["id"]

    await _insert_weekly_metrics(org_id=1, employee_id=employee_id, week_start=week_start)

    trained = await client.post(f"/api/v1/ops/clones/train?week_start={week_start.isoformat()}")
    assert trained.status_code == 200
    assert trained.json()["employees_scored"] >= 1

    scores = await client.get(f"/api/v1/ops/clones/scores?week_start={week_start.isoformat()}")
    assert scores.status_code == 200
    assert len(scores.json()) >= 1
    assert "overall_score" in scores.json()[0]

    summary = await client.get(f"/api/v1/ops/clones/summary?week_start={week_start.isoformat()}")
    assert summary.status_code == 200
    assert summary.json()["count"] >= 1

    dispatch = await client.post(
        "/api/v1/ops/clones/dispatch-plan",
        json={"challenge": "Complex tech architecture blocker", "week_start_date": week_start.isoformat(), "top_n": 2},
    )
    assert dispatch.status_code == 200
    assert len(dispatch.json()) >= 1
