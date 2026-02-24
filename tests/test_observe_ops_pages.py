from app.core.security import create_access_token


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )
    client.cookies.set("pc_session", token)


async def test_observe_page_loads_with_static_assets(client):
    _set_web_session(client)
    r = await client.get("/web/observe")
    assert r.status_code == 200
    assert "/static/css/observe.css" in r.text
    assert "/static/js/observe-page.js" in r.text


async def test_ops_intel_page_loads_with_static_assets(client):
    _set_web_session(client)
    r = await client.get("/web/ops-intel")
    assert r.status_code == 200
    assert "/static/css/ops_intel.css" in r.text
    assert "/static/js/ops-intel-page.js" in r.text
