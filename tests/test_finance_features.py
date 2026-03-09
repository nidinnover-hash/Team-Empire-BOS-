"""Tests for finance trends, budgets, and efficiency report."""
from __future__ import annotations

from datetime import date

import pytest

TODAY = date.today().isoformat()


def _income(amount: float, category: str = "consulting", desc: str = "Payment") -> dict:
    return {"type": "income", "amount": amount, "description": desc, "category": category, "entry_date": TODAY}


def _expense(amount: float, category: str = "office", desc: str = "Bill") -> dict:
    return {"type": "expense", "amount": amount, "description": desc, "category": category, "entry_date": TODAY}


# ── Monthly trends ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_finance_trends_empty(client):
    """Trends endpoint returns structure even with no data."""
    resp = await client.get("/api/v1/finance/trends?months=3")
    assert resp.status_code == 200
    data = resp.json()
    assert "months" in data
    assert "category_breakdown" in data
    assert "avg_monthly_income" in data
    assert "income_trend" in data


@pytest.mark.asyncio
async def test_finance_trends_with_data(client):
    """Trends reflect recorded entries."""
    await client.post("/api/v1/finance", json=_income(5000.0, "consulting", "Client payment"))
    await client.post("/api/v1/finance", json=_expense(1200.0, "office", "Office rent"))

    resp = await client.get("/api/v1/finance/trends?months=1")
    assert resp.status_code == 200
    data = resp.json()
    if data["months"]:
        m = data["months"][0]
        assert "income" in m
        assert "expense" in m
        assert "net" in m


# ── Budgets ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_budget(client):
    """Creating a budget returns it with current spend."""
    resp = await client.post("/api/v1/finance/budgets", json={
        "category": "software", "monthly_limit": 500.0, "description": "SaaS tools",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "software"
    assert data["monthly_limit"] == 500.0
    assert data["description"] == "SaaS tools"
    assert data["spent_this_month"] == 0.0
    assert data["remaining"] == 500.0
    assert data["pct_used"] == 0.0


@pytest.mark.asyncio
async def test_list_budgets(client):
    """List budgets returns all set budgets."""
    await client.post("/api/v1/finance/budgets", json={
        "category": "marketing", "monthly_limit": 1000.0,
    })
    await client.post("/api/v1/finance/budgets", json={
        "category": "hosting", "monthly_limit": 200.0,
    })

    resp = await client.get("/api/v1/finance/budgets")
    assert resp.status_code == 200
    budgets = resp.json()
    assert len(budgets) >= 2
    categories = [b["category"] for b in budgets]
    assert "marketing" in categories
    assert "hosting" in categories


@pytest.mark.asyncio
async def test_budget_tracks_spending(client):
    """Budget shows spending after recording an expense."""
    await client.post("/api/v1/finance/budgets", json={
        "category": "cloud", "monthly_limit": 300.0,
    })
    await client.post("/api/v1/finance", json=_expense(120.0, "cloud", "AWS bill"))

    resp = await client.get("/api/v1/finance/budgets")
    budgets = resp.json()
    cloud = [b for b in budgets if b["category"] == "cloud"]
    assert len(cloud) == 1
    assert cloud[0]["spent_this_month"] == 120.0
    assert cloud[0]["remaining"] == 180.0
    assert cloud[0]["pct_used"] == 40.0


# ── Efficiency report ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_efficiency_report_empty(client):
    """Efficiency report works with no data."""
    resp = await client.get("/api/v1/finance/efficiency?window_days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["efficiency_score"] == 100
    assert data["digital_expense_ratio"] == 0.0


@pytest.mark.asyncio
async def test_efficiency_report_with_digital_spend(client):
    """Efficiency report detects digital spend patterns."""
    await client.post("/api/v1/finance", json=_income(10000.0, "sales", "Revenue"))
    await client.post("/api/v1/finance", json=_expense(4000.0, "software", "OpenAI API usage"))

    resp = await client.get("/api/v1/finance/efficiency?window_days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["digital_expense_in_window"] == 4000.0
    assert data["digital_expense_ratio"] == 0.4
    assert data["efficiency_score"] < 100
    assert len(data["findings"]) >= 1


# ── Basic finance CRUD ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_finance_entries(client):
    """Create entries and list them."""
    r1 = await client.post("/api/v1/finance", json=_income(2500.0, "consulting"))
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/finance", json=_expense(300.0, "domain", "Domain renewal"))
    assert r2.status_code == 201

    resp = await client.get("/api/v1/finance")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 2


@pytest.mark.asyncio
async def test_finance_summary(client):
    """Summary totals income and expenses."""
    await client.post("/api/v1/finance", json=_income(8000.0, "consulting", "Project"))
    await client.post("/api/v1/finance", json=_expense(2000.0, "office", "Supplies"))

    resp = await client.get("/api/v1/finance/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_income"] >= 8000.0
    assert data["total_expense"] >= 2000.0
    assert data["balance"] == data["total_income"] - data["total_expense"]
