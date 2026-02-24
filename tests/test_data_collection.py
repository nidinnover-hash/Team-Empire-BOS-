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
    assert "key is required" in r.json()["detail"]


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
    assert "key must match" in r.json()["detail"]


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
    assert "context_type must be one of" in r.json()["detail"]
