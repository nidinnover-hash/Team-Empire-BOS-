"""Tests for Task → Project → Goal cascading progress logic."""
from __future__ import annotations

import pytest

# ── Project progress recalculation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_completion_updates_project_progress(client):
    """Completing a task recalculates project progress."""
    # Create a project
    proj = await client.post("/api/v1/projects", json={"title": "Cascade Test"})
    assert proj.status_code == 201
    pid = proj.json()["id"]
    assert proj.json()["progress"] == 0

    # Create 4 tasks in the project
    task_ids = []
    for i in range(4):
        t = await client.post("/api/v1/tasks", json={
            "title": f"Task {i}", "project_id": pid, "category": "business",
        })
        assert t.status_code == 201
        task_ids.append(t.json()["id"])

    # Complete 2 of 4 tasks → 50% progress
    for tid in task_ids[:2]:
        await client.patch(f"/api/v1/tasks/{tid}", json={"is_done": True})

    proj_resp = await client.get(f"/api/v1/projects/{pid}")
    assert proj_resp.json()["progress"] == 50
    assert proj_resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_all_tasks_done_completes_project(client):
    """Project auto-completes when all tasks are done."""
    proj = await client.post("/api/v1/projects", json={"title": "Auto Complete"})
    pid = proj.json()["id"]

    t1 = await client.post("/api/v1/tasks", json={
        "title": "Only task", "project_id": pid, "category": "business",
    })
    tid = t1.json()["id"]

    await client.patch(f"/api/v1/tasks/{tid}", json={"is_done": True})
    proj_resp = await client.get(f"/api/v1/projects/{pid}")
    assert proj_resp.json()["progress"] == 100
    assert proj_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_undoing_task_reactivates_project(client):
    """Uncompleting a task drops project progress and re-activates it."""
    proj = await client.post("/api/v1/projects", json={"title": "Undo Test"})
    pid = proj.json()["id"]

    t1 = await client.post("/api/v1/tasks", json={
        "title": "Task A", "project_id": pid, "category": "business",
    })
    tid = t1.json()["id"]

    # Complete → project completed
    await client.patch(f"/api/v1/tasks/{tid}", json={"is_done": True})
    assert (await client.get(f"/api/v1/projects/{pid}")).json()["status"] == "completed"

    # Undo → project reactivated
    await client.patch(f"/api/v1/tasks/{tid}", json={"is_done": False})
    resp = await client.get(f"/api/v1/projects/{pid}")
    assert resp.json()["progress"] == 0
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_delete_task_recalculates_project(client):
    """Deleting a task recalculates project progress."""
    proj = await client.post("/api/v1/projects", json={"title": "Delete Cascade"})
    pid = proj.json()["id"]

    t1 = await client.post("/api/v1/tasks", json={
        "title": "Keep", "project_id": pid, "category": "business",
    })
    t2 = await client.post("/api/v1/tasks", json={
        "title": "Remove", "project_id": pid, "category": "business",
    })

    # Complete first task (50%)
    await client.patch(f"/api/v1/tasks/{t1.json()['id']}", json={"is_done": True})
    assert (await client.get(f"/api/v1/projects/{pid}")).json()["progress"] == 50

    # Delete second task → only completed task remains → 100%
    await client.delete(f"/api/v1/tasks/{t2.json()['id']}")
    resp = await client.get(f"/api/v1/projects/{pid}")
    assert resp.json()["progress"] == 100


# ── Goal progress from project cascading ─────────────────────────────────────


@pytest.mark.asyncio
async def test_project_cascades_to_goal(client):
    """Project progress cascades to linked goal."""
    goal = await client.post("/api/v1/goals", json={"title": "Big Goal"})
    assert goal.status_code == 201
    gid = goal.json()["id"]

    # Create project linked to goal
    proj = await client.post("/api/v1/projects", json={
        "title": "Goal Project", "goal_id": gid,
    })
    pid = proj.json()["id"]
    assert proj.json()["goal_id"] == gid

    # Create and complete task
    t = await client.post("/api/v1/tasks", json={
        "title": "Goal Task", "project_id": pid, "category": "business",
    })
    await client.patch(f"/api/v1/tasks/{t.json()['id']}", json={"is_done": True})

    # Goal should be 100% and completed
    goal_resp = await client.get(f"/api/v1/goals/{gid}")
    assert goal_resp.json()["progress"] == 100
    assert goal_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_multiple_projects_average_goal_progress(client):
    """Goal progress is the average of linked project progresses."""
    goal = await client.post("/api/v1/goals", json={"title": "Multi Project Goal"})
    gid = goal.json()["id"]

    # Project 1: 2 tasks, complete 1 → 50%
    p1 = await client.post("/api/v1/projects", json={"title": "P1", "goal_id": gid})
    t1 = await client.post("/api/v1/tasks", json={"title": "P1T1", "project_id": p1.json()["id"], "category": "business"})
    await client.post("/api/v1/tasks", json={"title": "P1T2", "project_id": p1.json()["id"], "category": "business"})
    await client.patch(f"/api/v1/tasks/{t1.json()['id']}", json={"is_done": True})

    # Project 2: 1 task, complete it → 100%
    p2 = await client.post("/api/v1/projects", json={"title": "P2", "goal_id": gid})
    t3 = await client.post("/api/v1/tasks", json={"title": "P2T1", "project_id": p2.json()["id"], "category": "business"})
    await client.patch(f"/api/v1/tasks/{t3.json()['id']}", json={"is_done": True})

    # Goal: avg(50, 100) = 75%
    goal_resp = await client.get(f"/api/v1/goals/{gid}")
    assert goal_resp.json()["progress"] == 75
    assert goal_resp.json()["status"] == "active"  # Not all projects completed


@pytest.mark.asyncio
async def test_project_status_change_cascades_to_goal(client):
    """Manually completing a project cascades to goal."""
    goal = await client.post("/api/v1/goals", json={"title": "Status Goal"})
    gid = goal.json()["id"]

    proj = await client.post("/api/v1/projects", json={"title": "SP", "goal_id": gid})
    pid = proj.json()["id"]

    await client.patch(f"/api/v1/projects/{pid}/status", json={"status": "completed"})

    goal_resp = await client.get(f"/api/v1/goals/{gid}")
    assert goal_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_list_projects_by_goal(client):
    """Projects can be filtered by goal_id."""
    goal = await client.post("/api/v1/goals", json={"title": "Filter Goal"})
    gid = goal.json()["id"]

    await client.post("/api/v1/projects", json={"title": "Linked", "goal_id": gid})
    await client.post("/api/v1/projects", json={"title": "Unlinked"})

    resp = await client.get(f"/api/v1/projects?goal_id={gid}")
    projects = resp.json()
    assert all(p["goal_id"] == gid for p in projects)
    assert any(p["title"] == "Linked" for p in projects)


@pytest.mark.asyncio
async def test_project_progress_in_read_schema(client):
    """ProjectRead includes progress and goal_id fields."""
    proj = await client.post("/api/v1/projects", json={"title": "Schema Test"})
    data = proj.json()
    assert "progress" in data
    assert "goal_id" in data
    assert data["progress"] == 0
    assert data["goal_id"] is None
