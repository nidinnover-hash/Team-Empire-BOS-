# DeepSeek Strategy Prompts

## 1) Full Strategy Prompt
Use with repo context (docs + codebase summary).

```text
Act as a CTO + product strategist for this project.

Goals:
1) Evaluate product direction and market fit
2) Identify top technical and security risks
3) Create a practical 30/60/90-day execution plan
4) Define release-readiness criteria and KPIs
5) Prioritize roadmap using impact vs effort

Output format:
- Executive summary (max 10 bullets)
- P0/P1/P2 priorities with rationale
- Risks table: risk, impact, likelihood, mitigation, owner
- 30/60/90-day plan with weekly milestones
- Go-live checklist
- What to stop doing (de-scope list)

Constraints:
- Be concrete and opinionated
- Prefer actions that reduce risk and increase launch speed
- If data is missing, state assumptions explicitly
```

## 2) Technical-Only Prompt
```text
Act as principal engineer + security reviewer.
Audit architecture, integration reliability, and production hardening.
Return:
1) Top 10 technical risks (severity + probability + blast radius)
2) Immediate fixes (next 2 weeks)
3) Scalability plan (3 phases)
4) Observability/SLO plan
5) Test and release gate improvements
```

## 3) GTM-Only Prompt
```text
Act as B2B SaaS go-to-market strategist.
Define ICP, pricing, packaging, objections, and a 90-day launch plan.
Return:
1) ICP + positioning
2) Pricing and packaging tiers
3) Sales motion (founder-led)
4) Pilot offer + success metrics
5) Week-by-week GTM plan
```
