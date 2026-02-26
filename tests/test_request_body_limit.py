async def test_invalid_content_length_header_returns_400(client):
    req = client.build_request(
        "POST",
        "/api/v1/notifications/mark-read",
        headers={
            "Content-Type": "application/json",
            "Content-Length": "invalid",
        },
        content=b"{}",
    )
    resp = await client.send(req)
    assert resp.status_code == 400
    assert resp.json().get("detail") == "Invalid Content-Length header."
