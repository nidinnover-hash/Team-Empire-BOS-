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

from app.models.memory import ProfileMemory, TeamMember, DailyContext

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
                    [min(m.ai_level, 5)]
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
