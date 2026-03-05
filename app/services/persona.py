"""Persona dashboard — aggregation view across clone profiles, performance, and memory."""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clone_control import EmployeeCloneProfile
from app.models.clone_memory import CloneMemoryEntry
from app.models.clone_performance import ClonePerformanceWeekly
from app.models.employee import Employee
from app.schemas.persona import PersonaDashboard, PersonaKPIs, PersonaRow

logger = logging.getLogger(__name__)


async def get_persona_dashboard(
    db: AsyncSession,
    organization_id: int,
) -> PersonaDashboard:
    """Build the AI workforce readiness dashboard."""

    # 1. All employees with clone profiles
    profiles_result = await db.execute(
        select(
            EmployeeCloneProfile.employee_id,
            Employee.name,
            Employee.job_title,
        )
        .join(Employee, EmployeeCloneProfile.employee_id == Employee.id)
        .where(EmployeeCloneProfile.organization_id == organization_id)
    )
    profiles = profiles_result.all()  # list[(employee_id, name, job_title)]

    if not profiles:
        return PersonaDashboard(
            kpis=PersonaKPIs(total_clones=0, avg_ai_level=0.0, ready_count=0),
            rows=[],
        )

    employee_ids = [p[0] for p in profiles]

    # 2. Latest performance per employee — ROW_NUMBER() works in SQLite ≥ 3.25 and PostgreSQL
    perf_sq = (
        select(
            ClonePerformanceWeekly.employee_id,
            ClonePerformanceWeekly.overall_score,
            ClonePerformanceWeekly.readiness_level,
            func.row_number().over(
                partition_by=ClonePerformanceWeekly.employee_id,
                order_by=ClonePerformanceWeekly.week_start_date.desc(),
            ).label("rn"),
        )
        .where(
            ClonePerformanceWeekly.organization_id == organization_id,
            ClonePerformanceWeekly.employee_id.in_(employee_ids),
        )
        .subquery()
    )
    perf_result = await db.execute(
        select(
            perf_sq.c.employee_id,
            perf_sq.c.overall_score,
            perf_sq.c.readiness_level,
        ).where(perf_sq.c.rn == 1)
    )
    perf_map: dict[int, tuple[float, str]] = {
        emp_id: (float(score), str(readiness))
        for emp_id, score, readiness in perf_result.all()
    }

    # 3. Memory confidence aggregates per employee
    mem_result = await db.execute(
        select(
            CloneMemoryEntry.employee_id,
            func.avg(CloneMemoryEntry.confidence),
            func.count(CloneMemoryEntry.id),
        )
        .where(
            CloneMemoryEntry.organization_id == organization_id,
            CloneMemoryEntry.employee_id.in_(employee_ids),
        )
        .group_by(CloneMemoryEntry.employee_id)
    )
    mem_map: dict[int, tuple[float, int]] = {
        emp_id: (float(avg_conf), count)
        for emp_id, avg_conf, count in mem_result.all()
    }

    # 4. Assemble rows
    rows: list[PersonaRow] = []
    for emp_id, name, job_title in profiles:
        ai_level, readiness = perf_map.get(emp_id, (0.0, "developing"))
        confidence, memory_count = mem_map.get(emp_id, (0.0, 0))
        rows.append(PersonaRow(
            employee_id=emp_id,
            employee_name=name,
            job_title=job_title,
            ai_level=round(ai_level, 2),
            readiness=readiness,
            confidence=round(confidence, 2),
            memory_count=memory_count,
        ))

    # 5. Compute KPIs
    total_clones = len(rows)
    ai_levels = [r.ai_level for r in rows]
    avg_ai_level = round(sum(ai_levels) / total_clones, 2) if total_clones else 0.0
    ready_count = sum(1 for r in rows if r.readiness != "developing")

    return PersonaDashboard(
        kpis=PersonaKPIs(
            total_clones=total_clones,
            avg_ai_level=avg_ai_level,
            ready_count=ready_count,
        ),
        rows=rows,
    )
