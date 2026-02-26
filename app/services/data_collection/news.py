from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_collection import (
    NewsDigestItem,
    NewsDigestRequest,
    NewsDigestResult,
)
from app.services import memory as memory_service

# ── AI News Digest ─────────────────────────────────────────────────────────────

_NEWS_TOPICS: dict[str, dict[str, str | int]] = {
    "ai_agents": {
        "title": "AI Agents Are Taking Over Enterprise Workflows",
        "summary": "Companies are deploying autonomous AI agents for customer support, data analysis, and workflow automation, reducing manual overhead by 40-60%.",
        "tag": "AI Automation",
        "score": 95,
    },
    "llm_reasoning": {
        "title": "Next-Gen LLMs Show Human-Level Reasoning",
        "summary": "Latest LLM benchmarks show breakthrough performance on complex reasoning tasks, with implications for education, coding, and scientific research.",
        "tag": "AI Research",
        "score": 92,
    },
    "edtech_ai": {
        "title": "AI-Powered Education Platforms Reshape Overseas Admissions",
        "summary": "EdTech startups using AI for personalized student counseling and visa application automation see 3x conversion improvements.",
        "tag": "EdTech",
        "score": 90,
    },
    "personal_brand_ai": {
        "title": "Personal Branding with AI: The New CEO Playbook",
        "summary": "Founders using AI tools for content creation and personal brand management report 5x engagement growth on LinkedIn and X.",
        "tag": "Personal Branding",
        "score": 88,
    },
    "saas_automation": {
        "title": "SaaS Companies Embrace AI-First Architecture",
        "summary": "SaaS platforms built with AI at the core are outperforming traditional tools, offering predictive insights and automated decision-making.",
        "tag": "SaaS",
        "score": 85,
    },
    "clone_tech": {
        "title": "Digital Clone Technology Enters Mainstream Business",
        "summary": "Personal AI clones that handle communications, scheduling, and knowledge management are becoming essential tools for busy executives.",
        "tag": "AI Clones",
        "score": 93,
    },
    "cybersec_ai": {
        "title": "AI-Driven Cybersecurity Detects Threats 10x Faster",
        "summary": "Machine learning models now identify and respond to cyber threats in real-time, outperforming traditional rule-based systems.",
        "tag": "Cybersecurity",
        "score": 82,
    },
    "india_ai_boom": {
        "title": "India's AI Startup Ecosystem Hits Record Funding",
        "summary": "Indian AI startups raised $4.2B in the last quarter, with education, healthcare, and enterprise automation leading sectors.",
        "tag": "Startup Ecosystem",
        "score": 87,
    },
    "no_code_ai": {
        "title": "No-Code AI Platforms Democratize Business Automation",
        "summary": "Non-technical teams are building AI-powered workflows using drag-and-drop interfaces, accelerating digital transformation.",
        "tag": "Automation",
        "score": 78,
    },
    "ai_regulation": {
        "title": "Global AI Governance Frameworks Take Shape",
        "summary": "EU, US, and India propose new AI safety and compliance standards that will impact how businesses deploy and scale AI systems.",
        "tag": "AI Policy",
        "score": 75,
    },
    "voice_ai": {
        "title": "Voice AI Transforms Customer Interactions",
        "summary": "Conversational AI systems with near-human voice quality are replacing traditional IVR and call center operations.",
        "tag": "Voice AI",
        "score": 80,
    },
    "productivity_ai": {
        "title": "AI Productivity Tools Boost Executive Output by 3x",
        "summary": "CEOs and founders using AI assistants for email, task management, and decision support report significantly higher output.",
        "tag": "Productivity",
        "score": 86,
    },
}


async def generate_news_digest(
    db: AsyncSession,
    org_id: int,
    data: NewsDigestRequest,
) -> NewsDigestResult:
    interests = [i.strip().lower() for i in data.interests if i.strip()]
    if not interests:
        interests = ["artificial intelligence", "education", "startup"]

    # Score topics by relevance to interests
    scored: list[tuple[str, dict[str, str | int], int]] = []
    for topic_key, meta in _NEWS_TOPICS.items():
        title = str(meta["title"]).lower()
        summary = str(meta["summary"]).lower()
        combined = f"{title} {summary} {topic_key}"
        relevance = 0
        for interest in interests:
            tokens = interest.split()
            for token in tokens:
                if token in combined:
                    relevance += 10
        base_score = int(meta["score"])
        final_score = max(0, min(100, base_score + relevance))
        scored.append((topic_key, meta, final_score))

    scored.sort(key=lambda x: x[2], reverse=True)
    top_items = scored[:data.max_items]

    items = [
        NewsDigestItem(
            title=str(meta["title"]),
            summary=str(meta["summary"]),
            relevance_tag=str(meta["tag"]),
            relevance_score=score,
        )
        for _, meta, score in top_items
    ]

    # Feed top items into daily context
    matched_interests: list[str] = []
    memory_keys: list[str] = []
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")

    for idx, item in enumerate(items[:5], start=1):
        key = f"news.digest.{stamp}.{idx}"
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=key[:100],
            value=f"[{item.relevance_tag}] {item.title}: {item.summary[:150]}",
            category="news_digest",
        )
        memory_keys.append(key[:100])
        if item.relevance_tag not in matched_interests:
            matched_interests.append(item.relevance_tag)

    await db.commit()

    return NewsDigestResult(
        items=items,
        interests_matched=matched_interests,
        memory_keys=memory_keys,
        message=f"Generated {len(items)} AI news items tailored to your interests.",
    )
