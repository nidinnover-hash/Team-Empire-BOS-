from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_collection import BrandingPowerReport

# ── Personal Branding Power ───────────────────────────────────────────────────

_BRAND_THEMES: dict[str, tuple[str, ...]] = {
    "ai_tech": ("ai", "artificial intelligence", "llm", "machine learning", "automation", "saas"),
    "education": ("education", "student", "university", "learning", "admission", "visa"),
    "leadership": ("ceo", "founder", "leadership", "strategy", "vision", "growth"),
    "personal_dev": ("productivity", "mindset", "habit", "goal", "success", "discipline"),
    "innovation": ("startup", "innovation", "disrupt", "product", "launch", "scale"),
}


async def get_branding_power_report(
    db: AsyncSession,
    org_id: int,
) -> BrandingPowerReport:
    from app.models.memory import ProfileMemory
    from app.models.social import SocialPost

    today = date.today()
    since = today - timedelta(days=30)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=UTC)

    posts_result = await db.execute(
        select(SocialPost).where(
            SocialPost.organization_id == org_id,
            SocialPost.created_at >= since_dt,
        ).limit(500)
    )
    posts = list(posts_result.scalars().all())
    published = [p for p in posts if p.status == "published"]

    # Platform coverage
    platforms_active = list({p.platform for p in posts})
    all_platforms = {"instagram", "facebook", "linkedin", "x", "tiktok", "youtube"}
    platform_coverage = max(0, min(100, int((len(platforms_active) / max(len(all_platforms), 1)) * 100)))

    # Content themes
    all_content = " ".join(
        f"{p.title or ''} {p.content or ''}" for p in posts
    ).lower()
    matched_themes: list[str] = []
    for theme, keywords in _BRAND_THEMES.items():
        if any(kw in all_content for kw in keywords):
            matched_themes.append(theme.replace("_", " ").title())

    # Consistency: published ratio
    content_consistency = 0
    if posts:
        content_consistency = max(0, min(100, int((len(published) / len(posts)) * 100)))

    # Audience alignment from memory
    mem_result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == org_id,
            ProfileMemory.category == "learned",
        ).limit(100)
    )
    memories = list(mem_result.scalars().all())
    brand_memory_count = len([
        m for m in memories
        if any(kw in (m.value or "").lower() for kw in ("brand", "audience", "content", "social"))
    ])
    audience_alignment = max(0, min(100, 40 + brand_memory_count * 8))

    # Composite score
    branding_score = max(0, min(100, int(
        (content_consistency * 0.3) +
        (platform_coverage * 0.25) +
        (audience_alignment * 0.25) +
        (min(len(matched_themes) * 15, 100) * 0.2)
    )))

    strengths: list[str] = []
    gaps: list[str] = []
    if content_consistency >= 70:
        strengths.append("Strong content follow-through rate.")
    else:
        gaps.append("Improve draft-to-published conversion rate.")
    if platform_coverage >= 50:
        strengths.append("Good multi-platform presence.")
    else:
        gaps.append("Expand to more platforms for wider reach.")
    if matched_themes:
        strengths.append(f"Content covers key themes: {', '.join(matched_themes[:3])}.")
    else:
        gaps.append("Content lacks clear thematic focus areas.")
    if audience_alignment >= 60:
        strengths.append("Brand knowledge is well-integrated into clone memory.")
    else:
        gaps.append("Train clone with more brand-specific knowledge.")

    next_actions: list[str] = []
    if not published:
        next_actions.append("Publish your first piece of content to start building brand presence.")
    if len(platforms_active) < 3:
        next_actions.append("Expand to at least 3 platforms for consistent brand visibility.")
    if len(matched_themes) < 2:
        next_actions.append("Develop content pillars around 2-3 core themes.")
    if not next_actions:
        next_actions.append("Maintain consistency and track engagement metrics.")

    return BrandingPowerReport(
        branding_score=branding_score,
        content_consistency=content_consistency,
        platform_coverage=platform_coverage,
        audience_alignment=audience_alignment,
        total_posts_30d=len(posts),
        published_posts_30d=len(published),
        platforms_active=platforms_active,
        content_themes=matched_themes,
        strengths=strengths,
        gaps=gaps,
        next_actions=next_actions,
    )
