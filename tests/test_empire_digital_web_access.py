from app.core.security import create_access_token


def _set_web_session(client, *, user_id: int, email: str, role: str, org_id: int) -> None:
    token = create_access_token(
        {
            "id": user_id,
            "email": email,
            "role": role,
            "org_id": org_id,
            "token_version": 1,
        }
    )
    client.cookies.set("pc_session", token)


async def test_empire_digital_page_allows_ceo_and_manager(client):
    _set_web_session(client, user_id=1, email="ceo@org1.com", role="CEO", org_id=1)
    ceo_resp = await client.get("/web/empire-digital")
    assert ceo_resp.status_code == 200

    _set_web_session(client, user_id=3, email="manager@org1.com", role="MANAGER", org_id=1)
    mgr_resp = await client.get("/web/empire-digital")
    assert mgr_resp.status_code == 200


async def test_empire_digital_page_blocks_staff(client):
    _set_web_session(client, user_id=4, email="staff@org1.com", role="STAFF", org_id=1)
    resp = await client.get("/web/empire-digital")
    assert resp.status_code == 403
