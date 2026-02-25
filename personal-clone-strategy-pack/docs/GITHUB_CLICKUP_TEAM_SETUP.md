# GitHub + ClickUp Team Setup

This guide standardizes how the tech team uses GitHub with ClickUp.

## 1. Connect GitHub in ClickUp (Workspace-level)
- In ClickUp: `App Center -> GitHub -> Connect`.
- Use the Workspace connection (not personal) so all team members can use it.
- Authorize required org/repo access in GitHub.

## 2. Map Repositories
- In ClickUp integration settings, add all team repositories.
- Map each repo to the correct Space/List used by that team.

## 3. Enforce Task-ID Linking
This repository enforces ClickUp IDs on pull requests and commit messages.

Required format:
- `CU-123`

Rules:
- PR title must contain a ClickUp ID.
- Every commit message in PR must contain a ClickUp ID.

Examples:
- PR title: `CU-248 add unified inbox endpoint`
- Commit: `CU-248 add inbox schema and endpoint`
- Branch: `feature/CU-248-unified-inbox`

## 4. Recommended ClickUp Automations
- PR opened -> move task to `In Review`
- PR merged -> move task to `Done`
- PR closed without merge -> move task to `Blocked` (optional)

## 5. Rollout to Team
- Share this doc in your engineering channel.
- Ask each contributor to include `CU-xxx` in every PR title and commit.
- Block merges on failing `ClickUp ID Guard` workflow.

## 6. Troubleshooting
- Workflow fails with missing task ID:
  - Update PR title and/or rewrite commit messages to include `CU-xxx`.
- ClickUp task not linking:
  - Confirm GitHub app is connected at workspace level.
  - Confirm repository is added in ClickUp integration settings.
