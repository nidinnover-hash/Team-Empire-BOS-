# Multi-Business Management — Nidin BOS

Manage all your departments through one efficient BOS: **Tech**, **Recruitment**, **Study Abroad**, and **Sales & Marketing**. This doc describes how the BOS supports scaling across these different sectors professionally.

---

## The Four Sectors

| Sector | Company | BOS focus |
|--------|---------|------------|
| **Tech** | Codnov.ai | Product dev, engineering, GitHub/ClickUp sync, approvals, tasks, projects |
| **Recruitment** | EmpireO.ai (MEA) | Candidates, jobs, placements, routing rules, offer approvals |
| **Study Abroad** | ESA (Empire Study Abroad) | Applications, steps, deadlines, at-risk tracking, money approvals |
| **Sales & Marketing** | Empire Digital | Leads, deals, campaigns, contact policy, finance, money approvals |

Each sector is a separate **Organization** in BOS. Data is isolated by `organization_id` (tenant isolation). The **Control Dashboard** and **company switcher** in the sidebar let you focus on one company or (for CEO) aim for an all-companies view.

---

## How the BOS Serves Each Sector

### One platform, one control plane

- **Single login** — You (and your teams) use one BOS; the company switcher (EmpireO, ESA, Empire Digital, Codnov) sets context.
- **Single approval layer** — All high-risk actions (send email, execute workflow, money, offer) go through BOS Approvals. The Control Dashboard shows **Pending Approvals** across the active org.
- **Single audit trail** — Every mutation emits signals and audit events, so you have one place to see who did what and when.
- **Single RBAC** — Roles (CEO, ADMIN, MANAGER, STAFF) are enforced on every endpoint; no bypass.

### Sector-specific capabilities (already in BOS)

| Sector | What BOS provides |
|--------|--------------------|
| **Tech (Codnov)** | Tasks, projects, goals; GitHub/ClickUp snapshots; workflow runs; AI agents; approvals; observability |
| **Recruitment** | Contacts (candidates); recruitment routing rules; placements; placement confirmations; offer approvals via control API |
| **Study Abroad** | Study-abroad applications and steps; deadlines; at-risk count on Control Dashboard; money approvals |
| **Sales & Marketing** | Contacts, deals, pipeline; contact send policy; campaigns; finance summary; money approval matrix; lead routing (e.g. to ESA / EmpireO) |

### Control Dashboard (today)

- **Pending approvals** — Count and list for the current org.
- **Study Abroad at risk** — Steps past deadline not completed (current org).
- **Recent placements** — Last 7 days (current org).
- **Recent money approvals** — Last 7 days (current org).

Scoping is by your session’s **organization**. The sidebar company switcher (All Companies, EmpireO, ESA, Empire Digital, Codnov) is stored in the browser; backend APIs still use the logged-in user’s org. A future enhancement is a **CEO cross-org control summary** when “All Companies” is selected (aggregate across orgs the CEO can access).

---

## Scaling Professionally: Practices

1. **Use one org per company**  
   Keep EmpireO, ESA, Empire Digital, and Codnov as separate organizations. Use `industry_type` on `Organization` if you want sector filters or reports (e.g. `recruitment`, `study_abroad`, `marketing`, `tech`).

2. **Use departments inside an org**  
   The `Department` model (per-organization) supports internal structure (e.g. “Sales”, “Delivery”, “Engineering”). Use it for hierarchy and reporting within each company.

3. **Route work through BOS**  
   All controlled actions (sending, routing, offers, money) go through BOS control endpoints and approvals. See [CONTROL_APPS_INTEGRATION_CHECKLIST.md](CONTROL_APPS_INTEGRATION_CHECKLIST.md) and the per-app integration docs (Recruitment, Study Abroad, Marketing, Billing).

4. **One Control Dashboard habit**  
   Use Control Dashboard daily: clear pending approvals, review at-risk study-abroad steps, review recent placements and money approvals. Switch company in the sidebar to focus each sector.

5. **RBAC and audit**  
   Never relax RBAC; never skip audit. Every write must be tenant-scoped and recorded. That’s what makes the BOS safe to scale across sectors.

6. **Cross-company leads (Empire Digital)**  
   Lead routing and visibility are already defined in `app/core/lead_routing.py`: e.g. study_abroad → ESA, recruitment → EmpireO; Empire Digital as default lead owner. CEO (with Empire Digital org) can have cross-org visibility where implemented.

---

## Roadmap (optional enhancements)

- **CEO cross-org control summary** — When user is CEO and “All Companies” is selected, aggregate pending approvals, at-risk, placements, and money approvals across all accessible orgs.
- **Sector KPIs on Control** — Optional tiles or filters by sector (e.g. “Recruitment placements this week”, “Study Abroad at-risk”, “Tech pending approvals”).
- **Industry type on orgs** — Set `industry_type` for each organization (e.g. `tech`, `recruitment`, `study_abroad`, `marketing`) and use it in reports and filters.
- **Company switcher → backend** — Pass selected company (or “all”) to the API so that control and dashboard endpoints can scope or aggregate by selected context for users with multiple org access.

---

## Summary

You manage **Tech (Codnov), Recruitment (EmpireO), Study Abroad (ESA), and Sales & Marketing (Empire Digital)** through one BOS. Each sector is an organization; the same rules (tenant isolation, RBAC, approvals, audit) apply everywhere. Use the Control Dashboard and company switcher to operate and scale all four businesses from a single, professional control plane.
