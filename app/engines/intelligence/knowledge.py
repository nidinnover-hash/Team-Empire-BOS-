"""Knowledge Brain v2 — memory consolidation, knowledge extraction, and entity graph.

Provides three capabilities:
1. extract_knowledge_from_conversation() — pull facts/preferences/decisions from chat history
2. consolidate_memories() — merge duplicate/overlapping profile memory entries
3. build_knowledge_graph() — entity relationships from memory, contacts, and integrations
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any, TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import ProfileMemory

logger = logging.getLogger(__name__)

# Similarity threshold for merging profile memory entries.
MERGE_SIMILARITY_THRESHOLD = 0.75


class KnowledgeEntry(TypedDict):
    """A single piece of extracted knowledge from a conversation."""
    category: str       # "fact" | "preference" | "decision" | "goal" | "rule"
    key: str            # concise identifier, e.g. "revenue_target_q2"
    value: str          # the extracted knowledge text
    confidence: float   # 0.0-1.0


class EntityNode(TypedDict, total=False):
    """A node in the knowledge graph."""
    entity_type: str    # "person" | "company" | "integration" | "project" | "concept"
    name: str
    properties: dict[str, Any]


class EntityRelation(TypedDict):
    """A relationship between two entity nodes."""
    source: str         # entity name
    target: str         # entity name
    relation: str       # e.g. "manages", "uses", "works_on", "connected_to"
    weight: float       # 0.0-1.0


class KnowledgeGraph(TypedDict):
    """Simple entity-relationship graph built from memory."""
    nodes: list[EntityNode]
    edges: list[EntityRelation]
    generated_at: str


class ConsolidationResult(TypedDict):
    """Result of a memory consolidation run."""
    scanned: int
    merged: int
    deleted: int
    errors: int


# ── Knowledge Extraction ──────────────────────────────────────────────────────

def _extract_knowledge_heuristic(messages: list[dict[str, str]]) -> list[KnowledgeEntry]:
    """Extract knowledge entries from conversation using keyword heuristics.

    This is the fast, always-available fallback. Scans user messages for
    patterns that indicate facts, preferences, decisions, or goals.
    """
    entries: list[KnowledgeEntry] = []
    seen_keys: set[str] = set()

    _PREF_SIGNALS = ("i prefer", "i like", "i want", "always use", "never use", "i hate", "don't use")
    _FACT_SIGNALS = ("our revenue", "we have", "our team", "the company", "we use", "our budget",
                     "our clients", "our customers", "the deadline", "our goal")
    _DECISION_SIGNALS = ("i decided", "we decided", "let's go with", "approved", "rejected",
                         "i chose", "we chose", "going with", "moving forward with")
    _GOAL_SIGNALS = ("my goal", "our goal", "target is", "we need to", "objective is",
                     "aiming for", "planning to", "strategy is")

    for msg in messages:
        if msg.get("role") != "user":
            continue
        text = msg.get("content", "").strip()
        if not text or len(text) < 10:
            continue
        lower = text.lower()

        for signal in _PREF_SIGNALS:
            if signal in lower:
                key = f"pref_{_slugify(text[:60])}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    entries.append(KnowledgeEntry(
                        category="preference", key=key,
                        value=text[:300], confidence=0.6,
                    ))
                break

        for signal in _DECISION_SIGNALS:
            if signal in lower:
                key = f"decision_{_slugify(text[:60])}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    entries.append(KnowledgeEntry(
                        category="decision", key=key,
                        value=text[:300], confidence=0.65,
                    ))
                break

        for signal in _GOAL_SIGNALS:
            if signal in lower:
                key = f"goal_{_slugify(text[:60])}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    entries.append(KnowledgeEntry(
                        category="goal", key=key,
                        value=text[:300], confidence=0.6,
                    ))
                break

        for signal in _FACT_SIGNALS:
            if signal in lower:
                key = f"fact_{_slugify(text[:60])}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    entries.append(KnowledgeEntry(
                        category="fact", key=key,
                        value=text[:300], confidence=0.55,
                    ))
                break

    return entries


async def extract_knowledge_from_conversation(
    messages: list[dict[str, str]],
    *,
    use_ai: bool = True,
) -> list[KnowledgeEntry]:
    """Extract structured knowledge from a conversation history.

    Tries AI extraction first (if enabled), falls back to heuristic.
    Returns a list of KnowledgeEntry dicts ready for upsert into profile memory.
    """
    if not use_ai:
        return _extract_knowledge_heuristic(messages)

    try:
        from app.engines.brain.router import call_ai

        user_messages = [m["content"] for m in messages if m.get("role") == "user" and m.get("content")]
        if not user_messages:
            return []

        conversation_text = "\n---\n".join(user_messages[-10:])  # last 10 user messages
        prompt = (
            "Extract structured knowledge from this conversation. "
            "Return ONLY a JSON array. Each item must have: "
            '"category" (one of: fact, preference, decision, goal, rule), '
            '"key" (concise snake_case identifier), '
            '"value" (the knowledge text, max 200 chars), '
            '"confidence" (0.0-1.0). '
            "Only extract clearly stated information, not speculation.\n\n"
            f"Conversation:\n{conversation_text}"
        )

        raw = await call_ai(
            system_prompt="You are a knowledge extraction engine. Return only valid JSON arrays.",
            user_message=prompt,
            provider="openai",
            max_tokens=800,
        )

        parsed = _parse_extraction_response(raw)
        if parsed:
            return parsed
    except Exception:
        logger.debug("AI knowledge extraction failed, using heuristic", exc_info=True)

    return _extract_knowledge_heuristic(messages)


def _parse_extraction_response(raw: str) -> list[KnowledgeEntry]:
    """Parse AI response into KnowledgeEntry list. Returns empty on failure."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []

    if not isinstance(data, list):
        return []

    valid_categories = {"fact", "preference", "decision", "goal", "rule"}
    entries: list[KnowledgeEntry] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cat = str(item.get("category", "")).lower()
        if cat not in valid_categories:
            continue
        key = str(item.get("key", ""))[:120]
        value = str(item.get("value", ""))[:300]
        if not key or not value:
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        entries.append(KnowledgeEntry(
            category=cat, key=key, value=value, confidence=confidence,
        ))
    return entries


async def save_extracted_knowledge(
    db: AsyncSession,
    organization_id: int,
    entries: list[KnowledgeEntry],
    *,
    workspace_id: int | None = None,
) -> int:
    """Persist extracted knowledge entries into profile memory. Returns count saved."""
    from app.services.memory import upsert_profile_memory

    saved = 0
    for entry in entries:
        try:
            await upsert_profile_memory(
                db, organization_id=organization_id,
                key=entry["key"], value=entry["value"],
                category=entry["category"],
                workspace_id=workspace_id,
            )
            saved += 1
        except Exception:
            logger.debug("Failed to save knowledge entry %s", entry["key"], exc_info=True)
    return saved


# ── Memory Consolidation ──────────────────────────────────────────────────────

def _similarity(a: str, b: str) -> float:
    """Compute string similarity ratio between two texts."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _slugify(text: str) -> str:
    """Create a URL-safe slug from text."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())
    return slug.strip("_")[:80]


async def consolidate_memories(
    db: AsyncSession,
    organization_id: int,
    *,
    workspace_id: int | None = None,
    dry_run: bool = False,
) -> ConsolidationResult:
    """Merge duplicate/overlapping profile memory entries.

    Groups entries by category, then within each category finds pairs
    whose keys or values are highly similar. The newer entry's value
    is kept (or merged), and the older duplicate is deleted.
    """
    query = (
        select(ProfileMemory)
        .where(ProfileMemory.organization_id == organization_id)
        .order_by(ProfileMemory.category, ProfileMemory.updated_at.desc())
        .limit(1000)
    )
    if workspace_id is not None:
        query = query.where(ProfileMemory.workspace_id == workspace_id)

    result = await db.execute(query)
    all_entries = list(result.scalars().all())

    # Group by category
    by_category: dict[str | None, list[ProfileMemory]] = defaultdict(list)
    for entry in all_entries:
        by_category[entry.category].append(entry)

    merged = 0
    deleted = 0
    errors = 0
    to_delete: list[int] = []

    for _cat, entries in by_category.items():
        # Compare all pairs within category
        consumed: set[int] = set()
        for i, entry_a in enumerate(entries):
            if entry_a.id in consumed:
                continue
            for entry_b in entries[i + 1:]:
                if entry_b.id in consumed:
                    continue

                # Check key similarity
                key_sim = _similarity(entry_a.key, entry_b.key)
                # Check value similarity
                val_sim = _similarity(entry_a.value or "", entry_b.value or "")

                if key_sim >= MERGE_SIMILARITY_THRESHOLD or val_sim >= MERGE_SIMILARITY_THRESHOLD:
                    # Keep the newer entry (entry_a is newer due to ordering)
                    # If values differ significantly, append the old value
                    if val_sim < 0.9 and entry_b.value and entry_a.value:
                        combined = f"{entry_a.value}\n(Previously: {entry_b.value[:100]})"
                        if len(combined) <= 2000:
                            entry_a.value = combined
                            entry_a.updated_at = datetime.now(UTC)

                    to_delete.append(entry_b.id)
                    consumed.add(entry_b.id)
                    merged += 1

    if dry_run:
        return ConsolidationResult(
            scanned=len(all_entries), merged=merged, deleted=0, errors=0,
        )

    # Delete duplicates
    for entry_id in to_delete:
        try:
            entry = await db.get(ProfileMemory, entry_id)
            if entry and entry.organization_id == organization_id:
                await db.delete(entry)
                deleted += 1
        except Exception:
            logger.debug("Failed to delete merged entry %d", entry_id, exc_info=True)
            errors += 1

    if deleted > 0:
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("Consolidation commit failed", exc_info=True)
            errors += deleted
            deleted = 0

    return ConsolidationResult(
        scanned=len(all_entries), merged=merged, deleted=deleted, errors=errors,
    )


# ── Knowledge Graph ───────────────────────────────────────────────────────────

async def build_knowledge_graph(
    db: AsyncSession,
    organization_id: int,
    *,
    workspace_id: int | None = None,
) -> KnowledgeGraph:
    """Build a lightweight entity-relationship graph from memory, team, and integrations.

    The graph connects people, projects, integrations, and concepts based on
    co-occurrence in memory entries and explicit relationships (team.reports_to).
    """
    from app.models.memory import TeamMember
    from app.services.integration import list_integrations

    nodes: dict[str, EntityNode] = {}
    edges: list[EntityRelation] = []

    # ── Team members as person nodes ──
    team_query = (
        select(TeamMember)
        .where(TeamMember.organization_id == organization_id, TeamMember.is_active.is_(True))
        .limit(100)
    )
    team_rows = list((await db.execute(team_query)).scalars().all())

    for member in team_rows:
        node_name = member.name
        nodes[node_name] = EntityNode(
            entity_type="person", name=node_name,
            properties={
                "role": member.role_title or "",
                "team": member.team or "",
                "ai_level": member.ai_level or 0,
                "project": member.current_project or "",
            },
        )
        # Reports-to relationship
        if member.reports_to_id:
            manager = next((m for m in team_rows if m.id == member.reports_to_id), None)
            if manager:
                edges.append(EntityRelation(
                    source=node_name, target=manager.name,
                    relation="reports_to", weight=0.9,
                ))
        # Person -> project relationship
        if member.current_project:
            proj_name = member.current_project
            if proj_name not in nodes:
                nodes[proj_name] = EntityNode(
                    entity_type="project", name=proj_name, properties={},
                )
            edges.append(EntityRelation(
                source=node_name, target=proj_name,
                relation="works_on", weight=0.7,
            ))

    # ── Integrations as nodes ──
    try:
        integrations = await list_integrations(db, organization_id=organization_id)
        for integ in integrations:
            integ_name = integ.type
            nodes[integ_name] = EntityNode(
                entity_type="integration", name=integ_name,
                properties={"status": integ.status},
            )
    except Exception:
        logger.debug("Failed to load integrations for knowledge graph", exc_info=True)

    # ── Profile memory as concept nodes + edges ──
    mem_query = (
        select(ProfileMemory)
        .where(ProfileMemory.organization_id == organization_id)
        .order_by(ProfileMemory.updated_at.desc())
        .limit(200)
    )
    if workspace_id is not None:
        mem_query = mem_query.where(ProfileMemory.workspace_id == workspace_id)
    mem_rows = list((await db.execute(mem_query)).scalars().all())

    for mem in mem_rows:
        # Create concept node for categorized memories
        concept_name = mem.key
        if concept_name not in nodes:
            nodes[concept_name] = EntityNode(
                entity_type="concept", name=concept_name,
                properties={"category": mem.category or "general", "value_preview": (mem.value or "")[:100]},
            )

        # Link concepts to people/integrations if value mentions them
        value_lower = (mem.value or "").lower()
        for node_name, node in list(nodes.items()):
            if node["entity_type"] in ("person", "integration") and node_name.lower() in value_lower:
                edges.append(EntityRelation(
                    source=concept_name, target=node_name,
                    relation="mentions", weight=0.5,
                ))

    return KnowledgeGraph(
        nodes=list(nodes.values()),
        edges=edges,
        generated_at=datetime.now(UTC).isoformat(),
    )


# ── Knowledge-Enhanced Context Ranking ────────────────────────────────────────

async def rank_memories_by_relevance(
    db: AsyncSession,
    organization_id: int,
    query: str,
    memories: list[ProfileMemory],
    *,
    graph: KnowledgeGraph | None = None,
) -> list[ProfileMemory]:
    """Re-rank memory entries using knowledge graph connectivity.

    Memories that are connected to more entities mentioned in the query
    get a relevance boost. This supplements pure semantic similarity.
    """
    if not graph or not query or not memories:
        return memories

    query_lower = query.lower()

    # Find entities mentioned in the query
    mentioned_entities: set[str] = set()
    for node in graph["nodes"]:
        if node["name"].lower() in query_lower:
            mentioned_entities.add(node["name"])

    if not mentioned_entities:
        return memories

    # Build adjacency: concept -> set of connected entity names
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph["edges"]:
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])

    # Score each memory by graph connectivity to mentioned entities
    scored: list[tuple[float, ProfileMemory]] = []
    for mem in memories:
        connected = adjacency.get(mem.key, set())
        overlap = len(connected & mentioned_entities)
        # Base score 0, boost by number of connections to query-mentioned entities
        boost = overlap * 0.3
        scored.append((boost, mem))

    scored.sort(key=lambda x: -x[0])
    return [mem for _, mem in scored]
