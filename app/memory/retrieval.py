"""
Memory retrieval helpers — prevent context bloat and allow targeted lookups.

Problem: build_memory_context() in memory_service.py dumps ALL memory into
every AI call. As memory grows this wastes tokens and dilutes relevance.

These helpers let callers:
1. Filter memory to relevant categories only
2. Trim the assembled context string to a token-safe size
3. Build a focused context string from just the entries that matter
"""

from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Mapping
from typing import TypedDict

from app.models.memory import ProfileMemory, TeamMember, DailyContext


class ContextLayer(TypedDict, total=False):
    """Typed representation of a single context layer for structured AI injection."""
    layer_type: str      # "profile" | "team" | "daily" | "integration"
    source: str          # e.g. "clickup", "github", "slack", "manual"
    priority: int        # 1=critical … 5=background
    content: str         # the actual text block
    char_count: int
    score: float
    explain: list[str]
    created_at: str

# ── Constants ─────────────────────────────────────────────────────────────────

# Default character limit for injected memory context (~3 000 tokens ≈ 12 000 chars)
DEFAULT_CONTEXT_CHAR_LIMIT = 4_000

# Categories stored in ProfileMemory.category
MEMORY_CATEGORIES = {
    "assistant",   # things the agent has been told to remember
    "preference",  # user preferences
    "fact",        # facts about the org / domain
    "goal",        # current goals
    "rule",        # business rules / constraints
}

CRITICAL_SOURCES = {"priority", "blocker", "risk", "incident"}


def _parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def rank_context_layers(
    layers: list[ContextLayer],
    now: datetime | None = None,
    debug: bool = False,
) -> list[ContextLayer]:
    """
    Score and deterministically sort layers.

    Goals:
    - critical and fresher layers should rank higher
    - ties are stable and deterministic
    - optional debug explanations make ranking transparent
    """
    current = now or datetime.now(timezone.utc)
    ranked: list[ContextLayer] = []
    for layer in layers:
        reasons: list[str] = []
        priority = int(layer.get("priority", 5))
        score = 100.0 - (priority * 10.0)
        reasons.append(f"priority_base={score:.1f}")

        layer_type = str(layer.get("layer_type", "")).lower()
        source = str(layer.get("source", "")).lower()
        if layer_type == "daily":
            score += 12.0
            reasons.append("daily_boost=+12")
        if source in CRITICAL_SOURCES:
            score += 15.0
            reasons.append("critical_source_boost=+15")

        created_at = _parse_iso_utc(str(layer.get("created_at") or ""))
        if created_at is not None:
            age_hours = max(0.0, (current - created_at).total_seconds() / 3600.0)
            if age_hours > 0:
                decay = min(30.0, age_hours * 0.75)
                score -= decay
                reasons.append(f"age_decay=-{decay:.1f}")

        if layer_type == "integration":
            content = str(layer.get("content", "")).lower()
            if "disconnected" in content or "failed" in content:
                score += 6.0
                reasons.append("integration_risk_boost=+6")

        scored = ContextLayer(**layer)
        scored["score"] = round(score, 2)
        if debug:
            scored["explain"] = reasons
        ranked.append(scored)

    ranked.sort(
        key=lambda item: (
            -float(item.get("score", 0.0)),
            int(item.get("priority", 5)),
            str(item.get("layer_type", "")),
            str(item.get("source", "")),
            str(item.get("content", "")),
        )
    )
    return ranked


# ── Helpers ───────────────────────────────────────────────────────────────────

def filter_memory_by_category(
    entries: list[ProfileMemory],
    categories: list[str],
) -> list[ProfileMemory]:
    """
    Return only the ProfileMemory entries whose category is in the given list.
    Entries with no category (None) are always included.
    """
    cat_set = set(categories)
    return [e for e in entries if e.category is None or e.category in cat_set]


def trim_context_to_limit(
    context: str,
    char_limit: int = DEFAULT_CONTEXT_CHAR_LIMIT,
) -> str:
    """
    Trim a pre-built memory context string to at most char_limit characters.
    Trimming is done on whole lines to avoid cutting mid-sentence.
    Appends a notice so the AI knows context was truncated.
    """
    if len(context) <= char_limit:
        return context

    lines = context.splitlines(keepends=True)
    result: list[str] = []
    total = 0
    for line in lines:
        if total + len(line) > char_limit:
            break
        result.append(line)
        total += len(line)

    return "".join(result) + "\n[... memory truncated for length ...]\n"


def build_focused_context(
    profile_entries: list[ProfileMemory],
    team_members: list[TeamMember],
    daily_contexts: list[DailyContext],
    categories: list[str] | None = None,
    char_limit: int = DEFAULT_CONTEXT_CHAR_LIMIT,
) -> str:
    """
    Build a focused memory context string with optional category filtering
    and automatic size trimming.

    Args:
        profile_entries: All ProfileMemory rows for the org.
        team_members:    Active TeamMember rows for the org.
        daily_contexts:  Today's DailyContext rows for the org.
        categories:      If provided, only include profile entries in these categories.
        char_limit:      Maximum character length of the returned string.

    Returns:
        A formatted string ready for AI injection, trimmed to char_limit.
    """
    lines: list[str] = []

    # Profile memory — optionally filtered by category
    filtered = (
        filter_memory_by_category(profile_entries, categories)
        if categories
        else profile_entries
    )
    if filtered:
        lines.append("PROFILE:")
        for entry in filtered:
            lines.append(f"  - {entry.key}: {entry.value}")
        lines.append("")

    # Team members grouped by team
    if team_members:
        teams: dict[str, list[TeamMember]] = {}
        for m in team_members:
            key = m.team or "general"
            teams.setdefault(key, []).append(m)

        for team_name, members in sorted(teams.items()):
            lines.append(f"TEAM ({team_name}):")
            for m in members:
                ai_label = (
                    ["", "no AI", "basic AI", "intermediate AI", "advanced AI", "AI expert"]
                    [max(0, min(m.ai_level or 0, 5))]
                )
                project = f" | Project: {m.current_project}" if m.current_project else ""
                lines.append(
                    f"  - {m.name} | {m.role_title or 'Staff'} | {ai_label}{project}"
                )
        lines.append("")

    # Today's context
    if daily_contexts:
        lines.append("TODAY'S CONTEXT:")
        for ctx in daily_contexts:
            related = f" (re: {ctx.related_to})" if ctx.related_to else ""
            lines.append(f"  [{ctx.context_type.upper()}] {ctx.content}{related}")
        lines.append("")

    if not lines:
        return ""

    raw = "\n".join(lines)
    return trim_context_to_limit(raw, char_limit)


def build_typed_context(
    profile_entries: list[ProfileMemory],
    team_members: list[TeamMember],
    daily_contexts: list[DailyContext],
    integration_statuses: list[Mapping[str, object]] | None = None,
    categories: list[str] | None = None,
    char_limit: int = DEFAULT_CONTEXT_CHAR_LIMIT,
    debug: bool = False,
) -> list[ContextLayer]:
    """
    Build typed context layers — structured alternative to build_focused_context().
    Each layer has a type, source, priority, and content block.
    Layers are sorted by priority (lower = more important).
    """
    layers: list[ContextLayer] = []

    # Profile layer
    filtered = filter_memory_by_category(profile_entries, categories) if categories else profile_entries
    if filtered:
        content = "\n".join(f"  - {e.key}: {e.value}" for e in filtered)
        layers.append(ContextLayer(
            layer_type="profile", source="manual", priority=1,
            content=f"PROFILE:\n{content}", char_count=len(content),
        ))

    # Team layer
    if team_members:
        lines: list[str] = []
        for m in team_members:
            lines.append(f"  - {m.name} | {m.role_title or 'Staff'}")
        content = "\n".join(lines)
        layers.append(ContextLayer(
            layer_type="team", source="manual", priority=2,
            content=f"TEAM:\n{content}", char_count=len(content),
        ))

    # Daily context layers (one per context_type)
    ctx_groups: dict[str, list[str]] = {}
    for ctx in daily_contexts:
        ctx_groups.setdefault(ctx.context_type, []).append(ctx.content)
    for ctype, contents in ctx_groups.items():
        content = "\n".join(f"  {c}" for c in contents)
        layers.append(ContextLayer(
            layer_type="daily", source=ctype, priority=3,
            content=f"[{ctype.upper()}]:\n{content}",
            char_count=len(content),
            created_at=max((ctx.created_at for ctx in daily_contexts if ctx.context_type == ctype), default=None).isoformat() if any(ctx.context_type == ctype and ctx.created_at for ctx in daily_contexts) else "",
        ))

    # Integration layer
    if integration_statuses:
        integration_lines: list[str] = []
        for item in integration_statuses:
            name = str(item.get("type") or item.get("name") or "integration")
            status = str(item.get("status") or "unknown")
            last_sync = item.get("last_sync_at")
            suffix = f" | last_sync: {last_sync}" if last_sync else ""
            integration_lines.append(f"  - {name}: {status}{suffix}")
        content = "\n".join(integration_lines)
        layers.append(ContextLayer(
            layer_type="integration", source="integration", priority=4,
            content=f"INTEGRATIONS:\n{content}", char_count=len(content),
        ))

    # Score/sort, then trim total to char_limit
    layers = rank_context_layers(layers, debug=debug)
    total = 0
    kept: list[ContextLayer] = []
    for layer in layers:
        if total + layer.get("char_count", 0) > char_limit:
            break
        kept.append(layer)
        total += layer.get("char_count", 0)
    return kept
