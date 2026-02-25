# GitHub Organization Governance

## Overview

Automated governance for the `empireoe-ai` GitHub organization. Enforces team structure, repo permissions, branch protection, code ownership, and PR/issue templates across all repos.

## Organization Structure

| Role | GitHub Users | Org Role | Repo Access |
|------|-------------|----------|-------------|
| **Owners** | `nidin-cyber`, `empireadmincode` | Owner | Full admin |
| **Tech Lead** | `sharonempire` | Member | Admin (via `tech-leads` team) |
| **Developers** | `akshayempireoe`, `sanjayempire` | Member | Write (via `developers` team) |
| **Future** | `ashwini` | — | Add to `developers` team when ready |

## Teams

| Team | Members | Repo Permission |
|------|---------|----------------|
| `tech-leads` | sharonempire | `admin` |
| `developers` | akshayempireoe, sanjayempire | `push` (write) |

## Branch Protection (default branch: `main`)

All repos:
- Require pull requests (no direct pushes to main)
- Require at least **1 approval** (2 for critical repos)
- Require CODEOWNERS approval
- Dismiss stale reviews on new pushes
- Require CI status checks to pass
- Block force pushes
- Only `tech-leads` team can push to main

Critical repos (configured via `CRITICAL_GITHUB_REPOS`):
- Require **2 approvals** instead of 1

## CODEOWNERS

Auto-deployed to every repo at `.github/CODEOWNERS`:

```
* @sharonempire
/.github/ @nidin-cyber @sharonempire
/deploy/ @nidin-cyber @sharonempire
*.env* @nidin-cyber
```

## Templates

Deployed to every repo:
- `.github/pull_request_template.md` — PR checklist (tests, screenshots, linked ClickUp task)
- `.github/ISSUE_TEMPLATE/bug_report.md` — Bug report template
- `.github/ISSUE_TEMPLATE/feature_request.md` — Feature request template

## API Endpoints

### Apply Governance
```
POST /api/v1/github/apply-governance
Authorization: Bearer <CEO/ADMIN token>
```
Applies all governance rules. Idempotent — safe to run repeatedly. Returns a structured report.

### CEO Sync (Deep Data)
```
POST /api/v1/github/ceo-sync
Authorization: Bearer <CEO/ADMIN token>
```
Ingests repos, PRs (open + merged), reviews, commits per user/day, CI workflow runs.

### Weekly Summary
```
GET /api/v1/github/summary?range=7d
Authorization: Bearer <CEO/ADMIN token>
```
Returns: PR throughput per dev, avg review time, CI failure rate, blocked repos, inactive dev alerts, commit leaderboard.

### Risk Report
```
GET /api/v1/github/risks?range=7d
Authorization: Bearer <CEO/ADMIN token>
```
Returns: PRs without reviews, high CI failure repos, bus-factor repos (single contributor).

## Environment Variables

```bash
GITHUB_ORG=empireoe-ai                    # GitHub org login
CRITICAL_GITHUB_REPOS=empireoe-ai/webapp   # Comma-separated; get 2-approval requirement
```

The GitHub PAT must have these scopes:
- `admin:org` — create/manage teams
- `repo` — branch protection, file contents
- `read:user` — user verification

## Runbook

### First-time setup
```bash
# 1. Create a fine-grained PAT at https://github.com/settings/tokens
#    with admin:org + repo scopes for the empireoe-ai org

# 2. Connect GitHub via API
curl -X POST https://ai.empireoe.com/api/v1/integrations/github/connect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_token": "ghp_your_pat_here"}'

# 3. Apply governance
curl -X POST https://ai.empireoe.com/api/v1/github/apply-governance \
  -H "Authorization: Bearer $TOKEN"

# 4. Run CEO sync
curl -X POST https://ai.empireoe.com/api/v1/github/ceo-sync \
  -H "Authorization: Bearer $TOKEN"

# 5. Check summary
curl "https://ai.empireoe.com/api/v1/github/summary?range=7d" \
  -H "Authorization: Bearer $TOKEN"
```

### Adding a new team member
1. Add their GitHub username to `developers.members` in `github_governance.py`
2. Run `POST /api/v1/github/apply-governance`
3. They'll automatically get write access on all repos

### Adding a critical repo
1. Add `empireoe-ai/repo-name` to `CRITICAL_GITHUB_REPOS` in `.env`
2. Restart server
3. Run `POST /api/v1/github/apply-governance`
4. That repo will now require 2 approvals instead of 1

## DB Tables

| Table | Purpose |
|-------|---------|
| `github_repos` | Repo metadata (language, activity, stars) |
| `github_users` | Org members |
| `github_pull_requests` | PRs with state, review data, merge timestamps |
| `github_reviews` | Individual PR reviews (who approved, when) |
| `github_commits_daily` | Commit counts per author per day per repo |
| `github_workflow_runs` | CI/CD run status, duration, conclusion |
| `github_sync_runs` | Audit trail of each CEO sync run |
