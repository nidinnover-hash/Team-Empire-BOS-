from app.core.security import create_access_token


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )
    client.cookies.set("pc_session", token)
    client.cookies.set("pc_csrf", "csrf-test-token")


async def test_data_hub_page_requires_login(client):
    r = await client.get("/web/data-hub", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/web/login"


async def test_data_hub_page_loads_for_session(client):
    _set_web_session(client)
    r = await client.get("/web/data-hub")
    assert r.status_code == 200
    assert "Data Hub + Clone Playbook" in r.text
    assert "How to Use Clone Layer" in r.text
    assert "/static/css/data_hub.css" in r.text
    assert "/static/js/data-hub-page.js" in r.text


async def test_collect_data_into_daily_context(client):
    r = await client.post(
        "/api/v1/data/collect",
        json={
            "source": "meeting",
            "target": "daily_context",
            "content": "- Close admissions backlog\n- Confirm visa checklist owner",
            "context_type": "priority",
            "split_lines": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested_count"] == 2

    listed = await client.get("/api/v1/memory/context")
    assert listed.status_code == 200
    texts = [item["content"] for item in listed.json()]
    assert "Close admissions backlog" in texts


async def test_collect_data_profile_memory_requires_key(client):
    r = await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "profile_memory",
            "content": "Use concise updates",
            "split_lines": False,
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid request"


async def test_collect_data_profile_memory_rejects_unsafe_key(client):
    r = await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "profile_memory",
            "key": "bad key with spaces",
            "content": "Use concise updates",
            "split_lines": False,
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid request"


async def test_collect_data_daily_context_rejects_invalid_type(client):
    r = await client.post(
        "/api/v1/data/collect",
        json={
            "source": "meeting",
            "target": "daily_context",
            "content": "Important item",
            "context_type": "random_type",
            "split_lines": False,
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid request"


async def test_meeting_coach_generates_training_signals(client):
    r = await client.post(
        "/api/v1/data/meeting-coach",
        json={
            "objective": "sales",
            "speaker_name": "Sharon",
            "consent_confirmed": True,
            "transcript": (
                "Hi team, thanks for joining. Can you share your current admission goals? "
                "I understand your concern about budget and timeline. "
                "What outcome matters most in the next 90 days? "
                "Great, next step is I will send a proposal and confirm timeline by tomorrow."
            ),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tone_profile"] in {"consultative", "advisor-led", "pitch-heavy"}
    assert "sales_signals" in body
    assert body["memory_keys"]
    assert body["note_id"] is not None


async def test_meeting_coach_requires_consent(client):
    r = await client.post(
        "/api/v1/data/meeting-coach",
        json={
            "objective": "sales",
            "consent_confirmed": False,
            "transcript": "This transcript is long enough to pass minimum length but should fail due to consent.",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid request"


async def test_mobile_capture_analyze_feeds_memory_and_policy_layer(client):
    r = await client.post(
        "/api/v1/data/mobile-capture/analyze",
        json={
            "device_type": "mobile",
            "capture_type": "screenshot",
            "content_text": (
                "Project roadmap review and task deadline this week.\n"
                "Follow up client meeting notes and approval checklist.\n"
                "Gambling promo link and phishing scam message spotted."
            ),
            "wanted_topics": ["roadmap", "deadline", "client"],
            "unwanted_topics": ["gambling", "phishing"],
            "create_policy_drafts": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["wanted_count"] >= 2
    assert body["unwanted_count"] >= 1
    assert body["memory_keys"]
    assert body["policy_rule_ids"]
    assert body["note_id"] is not None


async def test_mobile_capture_upload_analyze_with_mocked_ocr(client, monkeypatch):
    from app.services import data_collection as data_collection_service

    def _fake_ocr(_payload: bytes) -> tuple[str, str]:
        return (
            "Deadline moved to Friday. Client follow-up required.\nPhishing link detected in screenshot.",
            "mock-ocr",
        )

    monkeypatch.setattr(data_collection_service, "extract_text_from_image_bytes", _fake_ocr)

    r = await client.post(
        "/api/v1/data/mobile-capture/upload-analyze",
        data={
            "device_type": "mobile",
            "capture_type": "screenshot",
            "wanted_topics": "deadline,client",
            "unwanted_topics": "phishing",
            "create_policy_drafts": "true",
        },
        files={"file": ("capture.png", b"fake-image-bytes", "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ocr_engine"] == "mock-ocr"
    assert body["filename"] == "capture.png"
    assert body["extracted_chars"] > 10
    assert body["wanted_count"] >= 1
    assert body["unwanted_count"] >= 1
