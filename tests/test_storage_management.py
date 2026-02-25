async def test_observability_storage_summary_shape(client):
    await client.post("/api/v1/tasks", json={"title": "Storage test task"})
    await client.post("/api/v1/notes", json={"content": "Storage test note"})

    response = await client.get("/api/v1/observability/storage")
    assert response.status_code == 200
    body = response.json()
    assert "org_id" in body
    assert "total_rows" in body
    assert "retention_days_chat" in body
    assert "tables" in body
    assert isinstance(body["tables"], list)
    assert any(item["table"] == "tasks" for item in body["tables"])
