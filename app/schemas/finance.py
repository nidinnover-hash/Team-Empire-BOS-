from datetime import datetime, date
from typing import Literal

from pydantic import BaseModel, Field

FinanceType = Literal["income", "expense"]
FinanceSeverity = Literal["low", "medium", "high"]


class FinanceEntryCreate(BaseModel):
    type: FinanceType
    amount: float = Field(gt=0)
    category: str  # salary | freelance | food | transport | housing | health | entertainment | other
    description: str | None = None
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
