from datetime import datetime, date
from pydantic import BaseModel, Field


class FinanceEntryCreate(BaseModel):
    type: str              # income | expense
    amount: float = Field(gt=0)
    category: str          # salary | freelance | food | transport | housing | health | entertainment | other
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
