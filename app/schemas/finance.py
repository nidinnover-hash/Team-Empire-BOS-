from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

FinanceType = Literal["income", "expense"]
FinanceSeverity = Literal["low", "medium", "high"]
FinanceCategory = Literal[
    "salary", "freelance", "sales", "consulting", "study",
    "food", "transport", "housing", "health", "entertainment",
    "software", "saas", "subscription", "cloud", "hosting",
    "ai", "ads", "marketing", "tools", "internet", "domain",
    "education", "office", "travel", "utilities", "other",
]


class FinanceEntryCreate(BaseModel):
    type: FinanceType
    amount: float = Field(gt=0, le=999_999_999.99)
    category: FinanceCategory
    description: str | None = Field(None, max_length=500)
    entry_date: date


class FinanceSummary(BaseModel):
    total_income: float
    total_expense: float
    balance: float


class FinanceEntryRead(BaseModel):
    id: int
    type: str
    amount: float
    category: str
    description: str | None
    entry_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


class FinanceEfficiencyFinding(BaseModel):
    code: str
    severity: FinanceSeverity
    message: str


class FinanceEfficiencyRecommendation(BaseModel):
    title: str
    action: str
    estimated_monthly_savings: float = 0.0


class FinanceEfficiencyReport(BaseModel):
    window_days: int
    income_in_window: float
    total_expense_in_window: float
    digital_expense_in_window: float
    digital_expense_ratio: float
    efficiency_score: int = Field(ge=0, le=100)
    findings: list[FinanceEfficiencyFinding]
    recommendations: list[FinanceEfficiencyRecommendation]


class MonthlyBreakdown(BaseModel):
    month: str  # "2026-03"
    income: float
    expense: float
    net: float


class CategoryBreakdown(BaseModel):
    category: str
    total: float
    count: int
    pct_of_total: float


class FinanceTrend(BaseModel):
    months: list[MonthlyBreakdown]
    category_breakdown: list[CategoryBreakdown]
    avg_monthly_income: float
    avg_monthly_expense: float
    income_trend: str  # "up" | "down" | "flat"
    expense_trend: str


class BudgetCreate(BaseModel):
    category: FinanceCategory
    monthly_limit: float = Field(gt=0, le=999_999_999.99)
    description: str | None = Field(None, max_length=200)


class BudgetRead(BaseModel):
    category: str
    monthly_limit: float
    description: str | None
    spent_this_month: float = 0.0
    remaining: float = 0.0
    pct_used: float = 0.0
