from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_collection import (
    MediaEditingLayerReport,
    MediaProjectCreate,
    MediaProjectOut,
)
from app.services import memory as memory_service

# ── Video & Audio Editing ──────────────────────────────────────────────────────

_QUALITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "high_production": ("4k", "hdr", "color grade", "b-roll", "cinematic", "professional", "studio"),
    "good_scripting": ("hook", "cta", "call to action", "intro", "outro", "structure", "story"),
    "seo_optimized": ("keyword", "seo", "thumbnail", "title", "description", "hashtag", "tag"),
    "engagement": ("question", "poll", "comment", "subscribe", "share", "like", "engage"),
    "branding": ("brand", "logo", "watermark", "intro", "signature", "style"),
}


def _score_media_quality(title: str, description: str, script: str | None, tags: str) -> tuple[int, list[str]]:
    combined = f"{title} {description} {script or ''} {tags}".lower()
    score = 40  # Base
    feedback: list[str] = []

    for category, keywords in _QUALITY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in combined)
        if hits >= 2:
            score += 12
            feedback.append(f"Strong {category.replace('_', ' ')} signals detected.")
        elif hits == 1:
            score += 6
        else:
            feedback.append(f"Consider improving {category.replace('_', ' ')}.")

    if script and len(script) >= 100:
        score += 5
        feedback.append("Script is well-developed.")
    elif not script:
        feedback.append("Add a script or outline for better content structure.")

    return max(0, min(100, score)), feedback


async def create_media_project(
    db: AsyncSession,
    org_id: int,
    data: MediaProjectCreate,
    actor_user_id: int | None,
) -> MediaProjectOut:
    from app.models.media_project import MediaProject

    quality_score, feedback = _score_media_quality(
        data.title, data.description, data.script_text, data.tags,
    )

    project = MediaProject(
        organization_id=org_id,
        title=data.title,
        media_type=data.media_type,
        platform=data.platform,
        description=data.description,
        duration_seconds=data.duration_seconds,
        script_text=data.script_text,
        tags=data.tags,
        quality_score=quality_score,
        feedback_json=json.dumps(feedback),
        created_by_user_id=actor_user_id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # Feed into memory
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    key = f"media.project.{data.media_type}.{stamp}"
    await memory_service.upsert_profile_memory(
        db=db,
        organization_id=org_id,
        key=key[:100],
        value=f"[{data.media_type}] {data.title}: quality={quality_score}/100",
        category="media_production",
    )
    await db.commit()

    return MediaProjectOut(
        id=int(project.id),
        title=project.title,
        media_type=project.media_type,
        platform=project.platform,
        description=project.description,
        status=project.status,
        duration_seconds=project.duration_seconds,
        script_text=project.script_text,
        tags=project.tags,
        quality_score=quality_score,
        feedback=feedback,
        created_at=project.created_at.isoformat() if project.created_at else "",
    )


async def get_media_editing_layer(
    db: AsyncSession,
    org_id: int,
) -> MediaEditingLayerReport:
    from app.models.media_project import MediaProject

    today = date.today()
    since = today - timedelta(days=30)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=UTC)

    result = await db.execute(
        select(MediaProject).where(
            MediaProject.organization_id == org_id,
            MediaProject.created_at >= since_dt,
        ).limit(500)
    )
    projects = list(result.scalars().all())

    published = [p for p in projects if p.status == "published"]
    drafts = [p for p in projects if p.status == "draft"]

    media_type_breakdown: dict[str, int] = {}
    platform_breakdown: dict[str, int] = {}
    total_quality = 0

    for p in projects:
        media_type_breakdown[p.media_type] = media_type_breakdown.get(p.media_type, 0) + 1
        platform_breakdown[p.platform] = platform_breakdown.get(p.platform, 0) + 1
        total_quality += p.quality_score

    avg_quality = int(total_quality / max(len(projects), 1))
    content_velocity = len(projects)

    # Editing score
    score = 30
    score += min(len(published) * 8, 25)
    score += min(avg_quality // 5, 15)
    score += min(len(media_type_breakdown) * 5, 15)
    score += min(content_velocity * 3, 15)
    score = max(0, min(100, score))

    strengths: list[str] = []
    gaps: list[str] = []

    if avg_quality >= 70:
        strengths.append("Consistently high content quality scores.")
    else:
        gaps.append("Improve content quality with better scripts and SEO optimization.")
    if len(media_type_breakdown) >= 3:
        strengths.append("Diverse media format portfolio.")
    else:
        gaps.append("Expand into more media formats (reels, podcasts, shorts).")
    if len(published) >= 3:
        strengths.append("Active publishing cadence.")
    else:
        gaps.append("Increase publishing frequency for better audience growth.")
    if any(k in media_type_breakdown for k in ("podcast", "audio")):
        strengths.append("Audio content presence for thought leadership.")

    next_actions: list[str] = []
    if not projects:
        next_actions.append("Create your first media project to start building content pipeline.")
    if len(drafts) > len(published):
        next_actions.append("Move draft projects through to publishing.")
    if avg_quality < 60:
        next_actions.append("Add hooks, CTAs, and SEO tags to boost quality scores.")
    if not next_actions:
        next_actions.append("Maintain production velocity and experiment with new formats.")

    return MediaEditingLayerReport(
        editing_score=score,
        total_projects_30d=len(projects),
        published_projects=len(published),
        draft_projects=len(drafts),
        avg_quality_score=avg_quality,
        media_type_breakdown=media_type_breakdown,
        platform_breakdown=platform_breakdown,
        content_velocity=content_velocity,
        strengths=strengths,
        gaps=gaps,
        next_actions=next_actions,
    )
