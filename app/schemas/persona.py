from pydantic import BaseModel


class PersonaRow(BaseModel):
    employee_id: int
    employee_name: str
    role: str | None
    ai_level: float
    readiness: str
    confidence: float
    memory_count: int


class PersonaKPIs(BaseModel):
    total_clones: int
    avg_ai_level: float
    ready_count: int


class PersonaDashboard(BaseModel):
    kpis: PersonaKPIs
    rows: list[PersonaRow]
