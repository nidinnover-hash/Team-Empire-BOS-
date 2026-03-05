from datetime import date


async def _create_contact(client, name: str, relationship: str, role: str | None = None, notes: str | None = None):
    return await client.post(
        "/api/v1/contacts",
        json={
            "name": name,
            "relationship": relationship,
            "role": role,
            "notes": notes,
        },
    )


async def _create_task(client, title: str, category: str = "business", due_date: str | None = None):
    payload = {"title": title, "category": category, "priority": 2}
    if due_date:
        payload["due_date"] = due_date
    return await client.post("/api/v1/tasks", json=payload)


async def _create_finance(client, type_: str, amount: float, category: str, description: str | None = None):
    return await client.post(
        "/api/v1/finance",
        json={
            "type": type_,
            "amount": amount,
            "category": category,
            "description": description,
            "entry_date": str(date.today()),
        },
    )


async def test_marketing_layer_endpoint_returns_report(client):
    await _create_contact(client, "Lead A", "business")
    await _create_contact(client, "Lead B", "business")
    await _create_task(client, "Follow up with lead A", "business")
    await _create_finance(client, "income", 10000, "sales", "consulting")
    await _create_finance(client, "expense", 1200, "marketing", "Meta ads")

    r = await client.get("/api/v1/layers/marketing")
    assert r.status_code == 200
    body = r.json()
    assert "readiness_score" in body
    assert "open_follow_up_tasks" in body
    assert "bottlenecks" in body
    assert "exposure_risk_level" in body
    assert "privacy_guardrails" in body
    assert "legal_guardrails" in body
    assert "account_guardrails" in body


async def test_study_layer_endpoint_returns_report(client):
    await _create_contact(client, "Student 1", "business", role="student", notes="Visa pending")
    await _create_task(client, "Admission checklist for student 1", "business", due_date=str(date.today()))
    await _create_finance(client, "income", 5000, "study", "student admission fee")

    r = await client.get("/api/v1/layers/study")
    assert r.status_code == 200
    body = r.json()
    assert "operational_score" in body
    assert body["study_pipeline_contacts"] >= 1
    assert "next_actions" in body


async def test_training_layer_endpoint_returns_report(client):
    await client.post(
        "/api/v1/memory/team",
        json={
            "name": "Dev A",
            "team": "tech",
            "role_title": "Developer",
            "ai_level": 2,
        },
    )
    await _create_task(client, "Training workshop for AI prompts", "business", due_date=str(date.today()))
    await client.post(
        "/api/v1/notes",
        json={"content": "Team completed learning session on agent workflows."},
    )

    r = await client.get("/api/v1/layers/training")
    assert r.status_code == 200
    body = r.json()
    assert "training_score" in body
    assert body["active_team_members"] >= 1
    assert "next_actions" in body


async def test_employee_performance_layer_endpoint_returns_report(client):
    await client.post(
        "/api/v1/memory/team",
        json={
            "name": "Ops Lead",
            "team": "ops",
            "role_title": "Operations Lead",
            "ai_level": 2,
            "current_project": "Admissions workflow",
            "notes": "blocked on vendor response",
        },
    )
    await client.post(
        "/api/v1/memory/team",
        json={
            "name": "Tech Lead",
            "team": "tech",
            "role_title": "Engineering Lead",
            "ai_level": 4,
            "current_project": "Automation pipeline",
        },
    )
    await _create_task(client, "Resolve onboarding queue", "business", due_date=str(date.today()))
    await _create_task(client, "Fix delayed approval tickets", "business", due_date=str(date.today()))
    await client.post(
        "/api/v1/memory/context",
        json={
            "date": str(date.today()),
            "context_type": "blocker",
            "content": "Vendor API quota is exhausted",
            "related_to": "integration",
        },
    )

    r = await client.get("/api/v1/layers/employee-performance")
    assert r.status_code == 200
    body = r.json()
    assert "performance_score" in body
    assert body["active_team_members"] == 2
    assert body["low_ai_members"] >= 1
    assert "members" in body
    assert len(body["members"]) == 2


async def test_employee_management_layer_endpoint_returns_report(client):
    await client.post(
        "/api/v1/ops/employees",
        json={"name": "Emp One", "email": "emp1@test.com", "github_username": "emp1-gh"},
    )
    await client.post(
        "/api/v1/ops/employees",
        json={"name": "Emp Two", "email": "emp2@test.com", "is_active": False},
    )
    await _create_task(client, "Backlog cleanup", "business")

    r = await client.get("/api/v1/layers/employee-management")
    assert r.status_code == 200
    body = r.json()
    assert "management_score" in body
    assert body["total_employees"] >= 2
    assert "top_risks" in body


async def test_revenue_management_layer_endpoint_returns_report(client):
    await _create_finance(client, "income", 15000, "sales", "enterprise billing")
    await _create_finance(client, "expense", 5000, "saas", "subscription stack")
    r = await client.get("/api/v1/layers/revenue-management")
    assert r.status_code == 200
    body = r.json()
    assert "revenue_health_score" in body
    assert "net_in_window" in body
    assert "next_actions" in body


async def test_training_staff_layer_endpoint_returns_report(client):
    await client.post(
        "/api/v1/memory/team",
        json={
            "name": "Staff A",
            "team": "ops",
            "role_title": "Coordinator",
            "ai_level": 2,
        },
    )
    await _create_task(client, "Staff training workshop", "business", due_date=str(date.today()))
    r = await client.get("/api/v1/layers/training-staff")
    assert r.status_code == 200
    body = r.json()
    assert "training_velocity_score" in body
    assert body["active_staff"] >= 1
    assert "top_risks" in body


async def test_ai_skill_routing_layer_endpoint_returns_report(client):
    await client.post(
        "/api/v1/memory/team",
        json={
            "name": "Growth Lead",
            "team": "sales",
            "role_title": "Sales Manager",
            "ai_level": 3,
            "current_project": "lead conversion automation",
            "notes": "focus on outreach workflow",
        },
    )
    r = await client.get("/api/v1/layers/ai-skill-routing")
    assert r.status_code == 200
    body = r.json()
    assert "routing_score" in body
    assert "members" in body


async def test_staff_prosperity_layer_endpoint_returns_report(client):
    await _create_finance(client, "income", 20000, "sales", "monthly revenue")
    await _create_finance(client, "expense", 8000, "operations", "team costs")
    await _create_task(client, "Resolve staff backlog", "business", due_date=str(date.today()))
    r = await client.get("/api/v1/layers/staff-prosperity")
    assert r.status_code == 200
    body = r.json()
    assert "composite_score" in body
    assert "ceo_message" in body


async def test_clone_training_layer_endpoint_returns_report(client):
    await client.post("/api/v1/ops/employees", json={"name": "Clone Emp", "email": "clone.emp@test.com", "job_title": "Developer"})
    r = await client.get("/api/v1/layers/clone-training")
    assert r.status_code == 200
    body = r.json()
    assert "clone_training_score" in body
    assert "members" in body


async def test_clone_marketing_sales_layer_endpoint_returns_report(client):
    await client.post("/api/v1/ops/employees", json={"name": "Sales Exec", "email": "sales.exec@test.com", "job_title": "Sales Manager"})
    await _create_contact(client, "Lead Z", "business", role="buyer", notes="needs conversion support")
    await _create_task(client, "Sales follow up lead z", "business")
    r = await client.get("/api/v1/layers/clone-marketing-sales")
    assert r.status_code == 200
    body = r.json()
    assert "lead_pipeline_health_score" in body
    assert "members" in body


async def test_opportunity_association_layer_endpoint_returns_report(client):
    await client.post("/api/v1/ops/employees", json={"name": "Ops Owner", "email": "ops.owner@test.com", "job_title": "Operations Manager"})
    await _create_contact(client, "University Partner", "business", role="admissions head", notes="student visa pipeline growth")
    r = await client.get("/api/v1/layers/opportunity-association")
    assert r.status_code == 200
    body = r.json()
    assert "association_score" in body
    assert "top_opportunities" in body
