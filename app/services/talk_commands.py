from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate
from app.services import clickup_service, do_service, github_service, slack_service
from app.services import finance as finance_service
from app.services import project as project_service
from app.services import task as task_service
from app.services import workspace as workspace_service


@dataclass(slots=True)
class TalkCommandResult:
    handled: bool
    response: str = ""
    role: str = "Ops Manager Clone"
    requires_approval: bool = False


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _extract_after(text: str, prefixes: tuple[str, ...]) -> str | None:
    raw = (text or "").strip()
    normalized = _norm(raw)
    for prefix in prefixes:
        if normalized.startswith(prefix):
            # Build a regex from the prefix words to match against raw text
            # (accounts for extra whitespace in the original input).
            words = prefix.split()
            pattern = r"\s+".join(re.escape(w) for w in words)
            m = re.match(pattern, raw, re.IGNORECASE)
            if m:
                tail = raw[m.end():].strip()
                return tail or None
    return None


def _find_platform(text: str) -> str | None:
    normalized = _norm(text)
    if _contains_any(normalized, ("github", "git hub")):
        return "github"
    if "clickup" in normalized:
        return "clickup"
    if _contains_any(normalized, ("digitalocean", "digital ocean", "do status", "do sync")):
        return "digitalocean"
    if "slack" in normalized:
        return "slack"
    return None


def _format_status_block(name: str, payload: dict[str, Any]) -> str:
    connected = bool(payload.get("connected"))
    last_sync = payload.get("last_sync_at") or "never"
    details: list[str] = []
    for key in ("login", "username", "team", "repos_tracked", "channels_tracked"):
        if payload.get(key) not in (None, ""):
            details.append(f"{key}={payload.get(key)}")
    detail_text = f" ({', '.join(details)})" if details else ""
    return f"- {name}: {'connected' if connected else 'not connected'}, last_sync={last_sync}{detail_text}"


async def _integration_status(db: AsyncSession, org_id: int, platform: str) -> TalkCommandResult:
    if platform == "github":
        status = await github_service.get_github_status(db, org_id)
    elif platform == "clickup":
        status = await clickup_service.get_clickup_status(db, org_id)
    elif platform == "digitalocean":
        status = await do_service.get_digitalocean_status(db, org_id)
    else:
        status = await slack_service.get_slack_status(db, org_id)
    return TalkCommandResult(handled=True, response=_format_status_block(platform, status))


async def _integration_sync(db: AsyncSession, org_id: int, platform: str) -> TalkCommandResult:
    if platform == "github":
        result = await github_service.sync_github(db, org_id=org_id)
        if result.get("error"):
            return TalkCommandResult(handled=True, response=f"GitHub sync failed: {result['error']}")
        return TalkCommandResult(
            handled=True,
            response=f"GitHub synced: PRs={result.get('prs_synced', 0)}, issues={result.get('issues_synced', 0)}.",
        )

    if platform == "clickup":
        result = await clickup_service.sync_clickup_tasks(db, org_id=org_id)
        if result.get("error"):
            return TalkCommandResult(handled=True, response=f"ClickUp sync failed: {result['error']}")
        return TalkCommandResult(
            handled=True,
            response=f"ClickUp synced: tasks={result.get('synced', 0)}.",
        )

    if platform == "digitalocean":
        result = await do_service.sync_digitalocean(db, org_id=org_id)
        if result.get("error"):
            return TalkCommandResult(handled=True, response=f"DigitalOcean sync failed: {result['error']}")
        droplets = result.get("droplets_synced", result.get("droplets", 0))
        members = result.get("team_members_synced", result.get("members", 0))
        return TalkCommandResult(
            handled=True,
            response=f"DigitalOcean synced: droplets={droplets}, team_members={members}.",
        )

    result = await slack_service.sync_slack_messages(db, org_id=org_id)
    if result.get("error"):
        return TalkCommandResult(handled=True, response=f"Slack sync failed: {result['error']}")
    return TalkCommandResult(
        handled=True,
        response=f"Slack synced: channels={result.get('channels_synced', 0)}, messages={result.get('messages_read', 0)}.",
    )


async def _all_integrations_status(db: AsyncSession, org_id: int) -> TalkCommandResult:
    statuses = {
        "github": await github_service.get_github_status(db, org_id),
        "clickup": await clickup_service.get_clickup_status(db, org_id),
        "digitalocean": await do_service.get_digitalocean_status(db, org_id),
        "slack": await slack_service.get_slack_status(db, org_id),
    }
    lines = ["Integration status summary:"]
    for name, payload in statuses.items():
        lines.append(_format_status_block(name, payload))
    return TalkCommandResult(handled=True, response="\n".join(lines))


async def maybe_handle_talk_command(
    db: AsyncSession,
    org_id: int,
    message: str,
    actor_role: str | None = None,
) -> TalkCommandResult:
    text = _norm(message)
    if not text:
        return TalkCommandResult(handled=False)
    default_workspace = await workspace_service.ensure_default_workspace(db, org_id)
    default_workspace_id = int(default_workspace.id)

    _PRIVILEGED_ROLES = {"CEO", "ADMIN", "MANAGER"}

    wants_status = _contains_any(text, (" status", "check status", "check integration", "health", "is connected", "connection status"))
    wants_sync = "sync" in text

    if _contains_any(text, ("all integrations", "integrations status", "integration status")) and wants_status:
        return await _all_integrations_status(db, org_id)

    platform = _find_platform(text)
    if platform and wants_status:
        return await _integration_status(db, org_id, platform)
    if platform and wants_sync:
        if actor_role not in _PRIVILEGED_ROLES:
            return TalkCommandResult(handled=True, response="Integration sync requires MANAGER role or above.")
        return await _integration_sync(db, org_id, platform)

    if _contains_any(text, ("expense", "expenses", "cost", "spend", "budget")) and _contains_any(
        text, ("api", "integration", "tracker", "summary", "status", "report")
    ):
        summary = await finance_service.get_summary(db, organization_id=org_id)
        efficiency = await finance_service.get_expenditure_efficiency(
            db,
            organization_id=org_id,
            window_days=30,
        )
        findings = ", ".join(item.code for item in efficiency.findings[:3]) or "none"
        return TalkCommandResult(
            handled=True,
            response=(
                "Expense tracker (30d snapshot):\n"
                f"- total_income: {summary.total_income:.2f}\n"
                f"- total_expense: {summary.total_expense:.2f}\n"
                f"- balance: {summary.balance:.2f}\n"
                f"- digital_expense_ratio: {efficiency.digital_expense_ratio:.2%}\n"
                f"- efficiency_score: {efficiency.efficiency_score}/100\n"
                f"- risk_flags: {findings}"
            ),
        )

    if text.startswith("list projects") or text == "projects":
        items = await project_service.list_projects(db, limit=10, organization_id=org_id)
        if not items:
            return TalkCommandResult(handled=True, response="No projects found.")
        rows = [f"- #{p.id} {p.title} [{p.status}]" for p in items]
        return TalkCommandResult(handled=True, response="Projects:\n" + "\n".join(rows))

    project_title = _extract_after(message, ("create project", "add project", "new project"))
    if project_title and actor_role not in _PRIVILEGED_ROLES:
        return TalkCommandResult(handled=True, response="Project creation requires MANAGER role or above.")
    if project_title:
        project = await project_service.create_project(
            db,
            ProjectCreate(title=project_title),  # type: ignore[call-arg]
            organization_id=org_id,
        )
        return TalkCommandResult(
            handled=True,
            response=f"Project created: #{project.id} {project.title} [{project.status}].",
        )

    if text.startswith("list tasks") or text == "tasks":
        tasks = await task_service.list_tasks(
            db,
            limit=10,
            organization_id=org_id,
            workspace_id=default_workspace_id,
            is_done=False,
        )
        if not tasks:
            return TalkCommandResult(handled=True, response="No open tasks found.")
        rows = [f"- #{t.id} {t.title} (priority {t.priority})" for t in tasks]
        return TalkCommandResult(handled=True, response="Open tasks:\n" + "\n".join(rows))

    task_title = _extract_after(message, ("create task", "add task", "new task"))
    if task_title and actor_role not in _PRIVILEGED_ROLES:
        return TalkCommandResult(handled=True, response="Task creation requires MANAGER role or above.")
    if task_title:
        task = await task_service.create_task(
            db,
            TaskCreate(title=task_title, category="business"),  # type: ignore[call-arg]
            organization_id=org_id,
            workspace_id=default_workspace_id,
        )
        return TalkCommandResult(
            handled=True,
            response=f"Task created: #{task.id} {task.title} (priority {task.priority}).",
        )

    if _contains_any(text, ("send slack", "message slack", "slack send")):
        return TalkCommandResult(
            handled=True,
            response=(
                "I can draft Slack messages in Talk Room. "
                "For safety, actual sending stays manual via /api/v1/integrations/slack/send."
            ),
            requires_approval=True,
        )

    return TalkCommandResult(handled=False)
