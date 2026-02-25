"""Tests for video/audio editing and social media management layers."""


# ── Media Project Creation ─────────────────────────────────────────────────────

async def test_create_media_project_video(client):
    r = await client.post(
        "/api/v1/data/media/projects",
        json={
            "title": "AI in Education: Complete Guide",
            "media_type": "video",
            "platform": "youtube",
            "description": "A cinematic 4k video with b-roll about AI in education. Hook intro, strong CTA.",
            "duration_seconds": 600,
            "script_text": (
                "Hook: Did you know AI is reshaping how students apply to universities? "
                "In this video we cover keyword SEO strategies for education content. "
                "Subscribe and share for more. Call to action at the end."
            ),
            "tags": "ai,education,youtube,seo,thumbnail",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "AI in Education: Complete Guide"
    assert body["media_type"] == "video"
    assert body["quality_score"] >= 50
    assert len(body["feedback"]) >= 1
    assert body["id"] >= 1


async def test_create_media_project_podcast(client):
    r = await client.post(
        "/api/v1/data/media/projects",
        json={
            "title": "Founder's Journey Episode 1",
            "media_type": "podcast",
            "platform": "youtube",
            "description": "A podcast about startup life and brand building",
            "tags": "podcast,brand,startup",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["media_type"] == "podcast"
    assert body["status"] == "draft"


async def test_create_media_project_reel(client):
    r = await client.post(
        "/api/v1/data/media/projects",
        json={
            "title": "Quick AI Tip #1",
            "media_type": "reel",
            "platform": "instagram",
            "description": "30 second reel with hook and CTA",
            "duration_seconds": 30,
            "tags": "reel,ai,tip,hashtag",
        },
    )
    assert r.status_code == 201
    assert r.json()["media_type"] == "reel"


async def test_create_media_project_audio(client):
    r = await client.post(
        "/api/v1/data/media/projects",
        json={
            "title": "Meditation Audio Track",
            "media_type": "audio",
            "platform": "other",
            "description": "Relaxation audio for personal brand",
        },
    )
    assert r.status_code == 201
    assert r.json()["media_type"] == "audio"


# ── Media Editing Layer Report ─────────────────────────────────────────────────

async def test_media_editing_layer_empty(client):
    r = await client.get("/api/v1/data/media/layer")
    assert r.status_code == 200
    body = r.json()
    assert "editing_score" in body
    assert 0 <= body["editing_score"] <= 100
    assert isinstance(body["media_type_breakdown"], dict)
    assert isinstance(body["strengths"], list)
    assert isinstance(body["gaps"], list)
    assert isinstance(body["next_actions"], list)


async def test_media_editing_layer_with_projects(client):
    # Create some projects first
    for mt in ["video", "podcast", "reel"]:
        await client.post(
            "/api/v1/data/media/projects",
            json={
                "title": f"Test {mt}",
                "media_type": mt,
                "platform": "youtube",
                "description": f"A {mt} with hook and CTA and keyword SEO",
                "tags": f"{mt},brand",
            },
        )

    r = await client.get("/api/v1/data/media/layer")
    assert r.status_code == 200
    body = r.json()
    assert body["total_projects_30d"] >= 3
    assert len(body["media_type_breakdown"]) >= 3
    assert body["content_velocity"] >= 3


async def test_media_editing_layer_via_layers(client):
    r = await client.get("/api/v1/layers/media-editing")
    assert r.status_code == 200
    body = r.json()
    assert "editing_score" in body


# ── Quality Scoring ────────────────────────────────────────────────────────────

async def test_media_quality_scoring():
    from app.services.data_collection import _score_media_quality

    score, feedback = _score_media_quality(
        "AI Video Guide",
        "4k cinematic b-roll with professional studio",
        "Hook: AI is changing everything. Subscribe and share. Call to action. SEO keyword.",
        "seo,thumbnail,hashtag",
    )
    assert score >= 60
    assert len(feedback) >= 1

    score2, feedback2 = _score_media_quality("Basic", "", None, "")
    assert score2 < score
    assert any("script" in f.lower() for f in feedback2)


# ── Social Media Management Layer ──────────────────────────────────────────────

async def test_social_management_layer_empty(client):
    r = await client.get("/api/v1/data/social/management-layer")
    assert r.status_code == 200
    body = r.json()
    assert "management_score" in body
    assert 0 <= body["management_score"] <= 100
    assert isinstance(body["platform_breakdown"], dict)
    assert isinstance(body["content_mode_breakdown"], dict)
    assert isinstance(body["strengths"], list)
    assert isinstance(body["gaps"], list)


async def test_social_management_layer_with_posts(client):
    # Create social posts
    for platform in ["linkedin", "x", "instagram"]:
        await client.post(
            "/api/v1/social/posts",
            json={
                "content_mode": "social_media",
                "platform": platform,
                "title": f"Post on {platform}",
                "content": f"Testing content for {platform}",
            },
        )

    r = await client.get("/api/v1/data/social/management-layer")
    assert r.status_code == 200
    body = r.json()
    assert body["total_posts_30d"] >= 3
    assert len(body["platform_breakdown"]) >= 3


async def test_social_management_layer_via_layers(client):
    r = await client.get("/api/v1/layers/social-management")
    assert r.status_code == 200
    body = r.json()
    assert "management_score" in body
    assert "publish_rate" in body
    assert "posting_consistency" in body
    assert "approval_pipeline_health" in body


async def test_social_management_publish_rate(client):
    # Create and publish a post
    r = await client.post(
        "/api/v1/social/posts",
        json={
            "content_mode": "social_media",
            "platform": "linkedin",
            "title": "Published Post",
            "content": "This will be published",
        },
    )
    assert r.status_code == 201
    post_id = r.json()["id"]

    # Approve then publish
    await client.post(f"/api/v1/social/posts/{post_id}/approve")
    await client.post(f"/api/v1/social/posts/{post_id}/publish")

    r = await client.get("/api/v1/data/social/management-layer")
    assert r.status_code == 200
    body = r.json()
    assert body["published_30d"] >= 1
