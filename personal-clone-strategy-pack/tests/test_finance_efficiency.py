from datetime import date, timedelta


async def _add_finance(client, type_: str, amount: float, category: str, description: str | None = None):
    payload = {
        "type": type_,
        "amount": amount,
        "category": category,
        "description": description,
        "entry_date": str(date.today()),
    }
    return await client.post("/api/v1/finance", json=payload)


async def test_finance_efficiency_returns_report(client):
    await _add_finance(client, "income", 10000, "salary", "monthly salary")
    await _add_finance(client, "expense", 1200, "software", "OpenAI API")
    await _add_finance(client, "expense", 800, "subscription", "SaaS monthly")
    await _add_finance(client, "expense", 900, "transport", "commute")

    r = await client.get("/api/v1/finance/efficiency?window_days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["window_days"] == 30
    assert body["income_in_window"] == 10000
    assert body["digital_expense_in_window"] == 2000
    assert 0 <= body["efficiency_score"] <= 100
    assert isinstance(body["recommendations"], list)
    assert body["recommendations"]


async def test_finance_efficiency_detects_no_income_risk(client):
    await _add_finance(client, "expense", 1500, "software", "cloud hosting")
    r = await client.get("/api/v1/finance/efficiency")
    assert r.status_code == 200
    body = r.json()
    assert body["income_in_window"] == 0
    assert body["digital_expense_in_window"] == 1500
    codes = {f["code"] for f in body["findings"]}
    assert "digital_spend_without_income" in codes


async def test_finance_efficiency_respects_window_filter(client):
    old_date = str(date.today() - timedelta(days=90))
    await client.post(
        "/api/v1/finance",
        json={
            "type": "income",
            "amount": 5000,
            "category": "salary",
            "description": "old income",
            "entry_date": old_date,
        },
    )
    await _add_finance(client, "income", 5000, "salary", "recent income")
    await _add_finance(client, "expense", 500, "software", "recent tool")

    r = await client.get("/api/v1/finance/efficiency?window_days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["income_in_window"] == 5000
    assert body["digital_expense_in_window"] == 500
