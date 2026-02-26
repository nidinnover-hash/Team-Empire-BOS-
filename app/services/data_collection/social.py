from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_collection import SocialManagementLayerReport

# ── Social Media Management Layer ──────────────────────────────────────────────


async def get_social_management_layer(
    db: AsyncSession,
    org_id: int,
) -> SocialManagementLayerReport:
    from app.models.social import SocialPost

    today = date.today()
    since = today - timedelta(days=30)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=UTC)

    result = await db.execute(
        select(SocialPost).where(
            SocialPost.organization_id == org_id,
            SocialPost.created_at >= since_dt,
        ).limit(500)
    )
    posts = list(result.scalars().all())

    published = [p for p in posts if p.status == "published"]
    drafts = [p for p in posts if p.status == "draft"]
    queued = [p for p in posts if p.status == "queued"]
    failed = [p for p in posts if p.status == "failed"]
    approved = [p for p in posts if p.status == "approved"]

    platform_breakdown: dict[str, int] = {}
    content_mode_breakdown: dict[str, int] = {}
    for p in posts:
        platform_breakdown[p.platform] = platform_breakdown.get(p.platform, 0) + 1
        content_mode_breakdown[p.content_mode] = content_mode_breakdown.get(p.content_mode, 0) + 1

    # Publish rate
    publish_rate = 0
    if posts:
        publish_rate = max(0, min(100, int((len(published) / len(posts)) * 100)))

    # Posting consistency: how spread out are posts across the 30 days
    posting_days = set()
    for p in posts:
        if p.created_at:
            posting_days.add(p.created_at.date() if hasattr(p.created_at, 'date') else p.created_at)
    posting_consistency = max(0, min(100, int((len(posting_days) / 30) * 100)))

    # Approval pipeline health
    pending_approval = len(queued) + len(approved)
    approval_pipeline_health = 100
    if pending_approval > 10:
        approval_pipeline_health = max(0, 100 - (pending_approval - 10) * 5)
    if failed:
        approval_pipeline_health = max(0, approval_pipeline_health - len(failed) * 10)

    # Management score
    score = 30
    score += min(publish_rate // 4, 20)
    score += min(posting_consistency // 5, 15)
    score += min(len(platform_breakdown) * 5, 15)
    score += min(approval_pipeline_health // 10, 10)
    score += min(len(published) * 2, 10)
    score = max(0, min(100, score))

    strengths: list[str] = []
    gaps: list[str] = []

    if publish_rate >= 60:
        strengths.append("Strong content publishing pipeline.")
    else:
        gaps.append("Improve draft-to-published conversion rate.")
    if posting_consistency >= 40:
        strengths.append("Good posting consistency throughout the month.")
    else:
        gaps.append("Post more consistently throughout the month.")
    if len(platform_breakdown) >= 3:
        strengths.append("Multi-platform social presence.")
    else:
        gaps.append("Expand to more social platforms.")
    if not failed:
        strengths.append("Zero failed posts — clean pipeline.")
    else:
        gaps.append(f"{len(failed)} failed post(s) — investigate and retry.")
    if approval_pipeline_health >= 80:
        strengths.append("Approval pipeline running smoothly.")
    else:
        gaps.append("Clear approval backlog to maintain pipeline health.")

    next_actions: list[str] = []
    if not posts:
        next_actions.append("Create and schedule your first social media post.")
    if len(drafts) > 5:
        next_actions.append(f"Review and advance {len(drafts)} draft posts.")
    if len(queued) > 5:
        next_actions.append(f"Approve {len(queued)} queued posts for publishing.")
    if posting_consistency < 30:
        next_actions.append("Set up a weekly content calendar for consistent posting.")
    if not next_actions:
        next_actions.append("Maintain posting cadence and track engagement.")

    return SocialManagementLayerReport(
        management_score=score,
        total_posts_30d=len(posts),
        published_30d=len(published),
        draft_30d=len(drafts),
        queued_30d=len(queued),
        failed_30d=len(failed),
        publish_rate=publish_rate,
        platform_breakdown=platform_breakdown,
        content_mode_breakdown=content_mode_breakdown,
        posting_consistency=posting_consistency,
        approval_pipeline_health=approval_pipeline_health,
        strengths=strengths,
        gaps=gaps,
        next_actions=next_actions,
    )
