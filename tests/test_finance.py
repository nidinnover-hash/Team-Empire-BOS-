from datetime import date

TODAY = str(date.today())


# ── GET /api/v1/finance/summary ──────────────────────────────────────────────

async def test_finance_summary_empty(client):
    response = await client.get("/api/v1/finance/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_income"] == 0.0
    assert body["total_expense"] == 0.0
    assert body["balance"] == 0.0


# ── POST /api/v1/finance ─────────────────────────────────────────────────────

async def test_create_income_entry_returns_201(client):
    response = await client.post(
        "/api/v1/finance",
        json={"type": "income", "amount": 5000.0, "category": "salary", "entry_date": TODAY},
    )
    assert response.status_code == 201


async def test_create_income_entry_returns_correct_fields(client):
    response = await client.post(
        "/api/v1/finance",
        json={"type": "income", "amount": 3000.0, "category": "freelance", "entry_date": TODAY},
    )
    body = response.json()
    assert body["type"] == "income"
    assert body["amount"] == 3000.0
    assert body["category"] == "freelance"
    assert body["entry_date"] == TODAY
    assert "id" in body
    assert "created_at" in body


async def test_create_expense_entry(client):
    response = await client.post(
        "/api/v1/finance",
        json={"type": "expense", "amount": 120.0, "category": "food", "entry_date": TODAY},
    )
    assert response.status_code == 201
    assert response.json()["type"] == "expense"


async def test_create_entry_zero_amount_rejected(client):
    response = await client.post(
        "/api/v1/finance",
        json={"type": "income", "amount": 0, "category": "salary", "entry_date": TODAY},
    )
    assert response.status_code == 422


async def test_create_entry_missing_fields_returns_422(client):
    response = await client.post("/api/v1/finance", json={"type": "income"})
    assert response.status_code == 422


# ── GET /api/v1/finance ──────────────────────────────────────────────────────

async def test_list_entries_empty(client):
    response = await client.get("/api/v1/finance")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_entries_returns_all(client):
    await client.post(
        "/api/v1/finance",
        json={"type": "income", "amount": 1000.0, "category": "salary", "entry_date": TODAY},
    )
    await client.post(
        "/api/v1/finance",
        json={"type": "expense", "amount": 200.0, "category": "food", "entry_date": TODAY},
    )
    items = (await client.get("/api/v1/finance")).json()
    assert len(items) == 2


# ── GET /api/v1/finance/summary (after entries) ──────────────────────────────

async def test_summary_reflects_entries(client):
    await client.post(
        "/api/v1/finance",
        json={"type": "income", "amount": 2000.0, "category": "salary", "entry_date": TODAY},
    )
    await client.post(
        "/api/v1/finance",
        json={"type": "expense", "amount": 500.0, "category": "food", "entry_date": TODAY},
    )
    body = (await client.get("/api/v1/finance/summary")).json()
    assert body["total_income"] == 2000.0
    assert body["total_expense"] == 500.0
    assert body["balance"] == 1500.0


# ── GET /api/v1/finance/efficiency ───────────────────────────────────────────

async def test_efficiency_report_returns_correct_shape(client):
    response = await client.get("/api/v1/finance/efficiency?window_days=30")
    assert response.status_code == 200
    body = response.json()
    assert "efficiency_score" in body
    assert "findings" in body
    assert "recommendations" in body
    assert 0 <= body["efficiency_score"] <= 100


async def test_efficiency_report_invalid_window_rejected(client):
    response = await client.get("/api/v1/finance/efficiency?window_days=3")
    assert response.status_code == 422
