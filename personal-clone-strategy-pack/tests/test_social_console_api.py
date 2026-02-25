from app.core.security import create_access_token


async def test_social_post_crud_and_summary(client):
    created = await client.post(
        "/api/v1/social/posts",
        json={
            "platform": "instagram",
            "title": "Scholarship campaign",
            "content": "Apply now for 2026 intake",
        },
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    listed = await client.get("/api/v1/social/posts")
    assert listed.status_code == 200
    assert any(item["id"] == post_id for item in listed.json())

    approved = await client.patch(
        f"/api/v1/social/posts/{post_id}/status",
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    summary = await client.get("/api/v1/social/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_posts"] >= 1
    assert "approved" in body


async def test_social_post_approve_and_publish_endpoints(client):
    created = await client.post(
        "/api/v1/social/posts",
        json={
            "platform": "linkedin",
            "title": "Offer update",
            "content": "New scholarship offer live",
        },
    )
    assert created.status_code == 201
    post_id = created.json()["id"]

    approved = await client.post(f"/api/v1/social/posts/{post_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    published = await client.post(f"/api/v1/social/posts/{post_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["published_at"] is not None


async def test_social_invalid_status_transition_returns_409(client):
    created = await client.post(
        "/api/v1/social/posts",
        json={
            "platform": "linkedin",
            "title": "Transition guard",
            "content": "Validate workflow transitions",
        },
    )
    assert created.status_code == 201
    post_id = created.json()["id"]

    # draft -> published is blocked; must go via approved/queued flow
    invalid = await client.patch(
        f"/api/v1/social/posts/{post_id}/status",
        json={"status": "published"},
    )
    assert invalid.status_code == 409


async def test_social_mode_platform_distinction_enforced(client):
    # Valid social media post
    ok_social = await client.post(
        "/api/v1/social/posts",
        json={
            "content_mode": "social_media",
            "platform": "instagram",
            "title": "Campus update",
            "content": "New intake open",
        },
    )
    assert ok_social.status_code == 201

    # Invalid: entertainment platform inside social_media mode
    bad_social = await client.post(
        "/api/v1/social/posts",
        json={
            "content_mode": "social_media",
            "platform": "youtube",
            "title": "Wrong lane",
            "content": "This should fail",
        },
    )
    assert bad_social.status_code == 422

    # Entertainment mode is blocked for professional login by strict purpose barrier
    blocked_ent = await client.post(
        "/api/v1/social/posts",
        json={
            "content_mode": "entertainment",
            "platform": "youtube",
            "title": "Blocked lane",
            "content": "Should be blocked for professional login",
        },
    )
    assert blocked_ent.status_code == 403

    # Valid entertainment post for entertainment-purpose login
    ent_token = create_access_token(
        {
            "id": 1,
            "email": "ceo@org1.com",
            "role": "CEO",
            "org_id": 1,
            "token_version": 1,
            "purpose": "entertainment",
            "default_theme": "dark",
            "default_avatar_mode": "entertainment",
        }
    )
    ok_ent = await client.post(
        "/api/v1/social/posts",
        json={
            "content_mode": "entertainment",
            "platform": "youtube",
            "title": "Trailer",
            "content": "Watch now",
        },
        headers={"Authorization": f"Bearer {ent_token}"},
    )
    assert ok_ent.status_code == 201
