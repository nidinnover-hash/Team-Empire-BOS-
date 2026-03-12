# Improvements We Can Make

Prioritized list of improvements for Nidin BOS: multi-business control, control levers, tenant/quality, and UX.

---

## 1. Multi-business & control plane

| Improvement | What | Why |
|-------------|------|-----|
| **CEO cross-org control summary** | When user is CEO and company switcher is “All Companies”, aggregate pending approvals, study-abroad at-risk, placements, and money approvals across all orgs the CEO can access. | Today the Control Dashboard only shows the session org; you have to switch company to see each sector. |
| **Company switcher → backend** | Send selected company (or “all”) to the API (header or query) so control and dashboard endpoints can scope or aggregate by that context. | Switcher is currently UI-only (localStorage); backend always uses session org. |
| **Sector KPIs on Control** | Tiles or filters by sector (e.g. “Recruitment placements this week”, “Study Abroad at-risk”, “Tech pending approvals”). | Single view per sector without switching. |
| **Set industry_type on orgs** | Populate `Organization.industry_type` (e.g. `tech`, `recruitment`, `study_abroad`, `marketing`) and use it in reports and filters. | Enables sector-level reporting and filters. |

---

## 2. Control levers & policy (from PENDING_IMPROVEMENTS)

| Improvement | What | Why |
|-------------|------|-----|
| **can_send — real contact policy** | Implement real contact send policy and rate limits (DB/config), not just stub “allowed + now”. | Safe, consistent control over who can send what and how often. |
| **route_lead — richer rules** | Rules by region/lead_type and SLA config per org. | More precise lead routing and SLA by sector. |
| **Study abroad — real milestones** | Application/milestone model with real deadlines (replace stubs). | Control Dashboard at-risk and integrations depend on real data. |
| **Money approvals — approval matrix** | Use approval matrix by role/amount (config) for money flows. | Consistent approval thresholds across sectors. |

---

## 3. Architecture, tenant & quality

| Improvement | What | Why |
|-------------|------|-----|
| **Layers_pkg tenant checks** | Audit `app/services/layers_pkg/people.py` and `clone.py`: ensure every `select(Task)` and `select(Contact)` includes org filter. | CLAUDE.md calls this out; prevents cross-org leaks. |
| **Staging gate extension** | Fail deploy if new money/communications flows skip approvals (beyond current guards). | Ensures no approval bypass in new code. |
| **Optional org_id cleanup** | If any service still has `organization_id: int \| None`, make it required and fix callers. | Tenant isolation is non-negotiable. |

---

## 4. Recruitment & study abroad (optional)

| Improvement | What | Why |
|-------------|------|-----|
| **Recruitment routing rules** | Richer rules (e.g. by region/product_line) and SLA config per org. | Better candidate assignment and SLA by business line. |
| **Study abroad integration** | Wire real application/milestone data to control levers and Control Dashboard. | End-to-end study-abroad control and at-risk visibility. |

---

## 5. UX & observability

| Improvement | What | Why |
|-------------|------|-----|
| **Control Dashboard links** | Make approval IDs and placement rows clickable (e.g. to approval review or placement detail). | Faster triage from one screen. |
| **Control report by org** | Observability report already has event counts by type and org; ensure Control Dashboard or a dedicated page can show it. | Visibility into activity per sector. |

---

## Suggested order to tackle

1. **Quick wins:** Set `industry_type` on orgs; add links on Control Dashboard for approvals/placements.
2. **High impact:** CEO cross-org control summary + company switcher to backend (so “All Companies” works).
3. **Control & safety:** Real `can_send` policy, money approval matrix, study-abroad real milestones.
4. **Hardening:** Layers_pkg tenant audit, staging gate extension.

Existing doc: [PENDING_IMPROVEMENTS.md](PENDING_IMPROVEMENTS.md). Multi-business context: [MULTI_BUSINESS_MANAGEMENT.md](MULTI_BUSINESS_MANAGEMENT.md).
