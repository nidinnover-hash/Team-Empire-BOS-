from app.core.security import create_access_token


def _set_web_session(client, *, user_id: int, email: str, role: str, org_id: int = 1) -> None:
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


async def test_contacts_page_staff_shows_restricted_pipeline_markers(client):
    _set_web_session(client, user_id=4, email="staff@org1.com", role="STAFF")
    response = await client.get("/web/contacts")
    assert response.status_code == 200
    assert "Restricted for your role" in response.text
    assert "Pipeline Value" in response.text
    assert "Restricted" in response.text


async def test_contacts_page_admin_does_not_render_restricted_pipeline_marker(client):
    _set_web_session(client, user_id=6, email="admin@org1.com", role="ADMIN")
    response = await client.get("/web/contacts")
    assert response.status_code == 200
    assert "Restricted for your role" not in response.text
