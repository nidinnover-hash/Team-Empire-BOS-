"""Tests for the media storage system — upload, list, search, analyze, delete."""

import io
import json
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import media_agent, media_storage

# ── Helpers ──────────────────────────────────────────────────────────


def _fake_upload(filename: str = "test.png", mime: str = "image/png", size: int = 1024):
    """Build a multipart files tuple for httpx."""
    content = b"x" * size
    return {"file": (filename, io.BytesIO(content), mime)}


# ── Upload Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_image(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    resp = await client.post("/api/v1/media/upload", files=_fake_upload())
    assert resp.status_code == 201
    data = resp.json()
    assert data["original_name"] == "test.png"
    assert data["mime_type"] == "image/png"
    assert data["file_size_bytes"] == 1024
    assert data["storage_backend"] == "local"
    assert data["is_processed"] is False


@pytest.mark.asyncio
async def test_upload_pdf(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    resp = await client.post(
        "/api/v1/media/upload",
        files=_fake_upload("report.pdf", "application/pdf", 2048),
    )
    assert resp.status_code == 201
    assert resp.json()["mime_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_upload_video(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    resp = await client.post(
        "/api/v1/media/upload",
        files=_fake_upload("clip.mp4", "video/mp4", 4096),
    )
    assert resp.status_code == 201
    assert resp.json()["mime_type"] == "video/mp4"


@pytest.mark.asyncio
async def test_upload_disallowed_mime(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    resp = await client.post(
        "/api/v1/media/upload",
        files=_fake_upload("hack.exe", "application/x-msdownload", 512),
    )
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_oversized_file(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(media_storage, "MAX_UPLOAD_BYTES", 500)
    resp = await client.post(
        "/api/v1/media/upload",
        files=_fake_upload("big.png", "image/png", 1024),
    )
    assert resp.status_code == 400
    assert "too large" in resp.json()["detail"].lower()


# ── Bulk Upload ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_upload(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    files = [
        ("files", ("a.png", io.BytesIO(b"aaa"), "image/png")),
        ("files", ("b.jpg", io.BytesIO(b"bbb"), "image/jpeg")),
    ]
    resp = await client.post("/api/v1/media/upload/bulk", files=files)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 2
    assert data[0]["original_name"] == "a.png"
    assert data[1]["original_name"] == "b.jpg"


# ── List / Get / Download ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_media(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    # Upload two files first
    await client.post("/api/v1/media/upload", files=_fake_upload("a.png"))
    await client.post("/api/v1/media/upload", files=_fake_upload("b.pdf", "application/pdf"))

    resp = await client.get("/api/v1/media?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_media_mime_filter(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    await client.post("/api/v1/media/upload", files=_fake_upload("a.png"))
    await client.post("/api/v1/media/upload", files=_fake_upload("b.pdf", "application/pdf"))

    resp = await client.get("/api/v1/media?mime_prefix=image/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_list_media_pagination(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    for i in range(5):
        await client.post("/api/v1/media/upload", files=_fake_upload(f"f{i}.png"))

    resp = await client.get("/api/v1/media?skip=0&limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp2 = await client.get("/api/v1/media?skip=2&limit=2")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 2


@pytest.mark.asyncio
async def test_get_media_detail(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    upload_resp = await client.post("/api/v1/media/upload", files=_fake_upload())
    mid = upload_resp.json()["id"]

    resp = await client.get(f"/api/v1/media/{mid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == mid
    assert resp.json()["original_name"] == "test.png"


@pytest.mark.asyncio
async def test_get_media_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/media/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_media(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    upload_resp = await client.post("/api/v1/media/upload", files=_fake_upload("pic.png", "image/png", 256))
    mid = upload_resp.json()["id"]

    resp = await client.get(f"/api/v1/media/{mid}/download")
    assert resp.status_code == 200
    assert len(resp.content) == 256


@pytest.mark.asyncio
async def test_download_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/media/99999/download")
    assert resp.status_code == 404


# ── Delete ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_media(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    upload_resp = await client.post("/api/v1/media/upload", files=_fake_upload())
    mid = upload_resp.json()["id"]

    resp = await client.delete(f"/api/v1/media/{mid}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Should not appear in list after soft delete
    list_resp = await client.get("/api/v1/media")
    assert all(item["id"] != mid for item in list_resp.json())


@pytest.mark.asyncio
async def test_delete_not_found(client: AsyncClient):
    resp = await client.delete("/api/v1/media/99999")
    assert resp.status_code == 404


# ── Update / Patch ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_media_entity_linkage(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    upload_resp = await client.post("/api/v1/media/upload", files=_fake_upload())
    mid = upload_resp.json()["id"]

    resp = await client.patch(f"/api/v1/media/{mid}?entity_type=employee&entity_id=42")
    assert resp.status_code == 200
    assert resp.json()["entity_type"] == "employee"
    assert resp.json()["entity_id"] == 42


# ── AI Analyze ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_media(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))

    # Mock the AI call
    fake_ai_result = json.dumps({
        "tags": ["logo", "branding"],
        "description": "Company logo image",
        "category": "photo",
    })

    async def fake_call_ai(system_prompt, user_message):
        return fake_ai_result

    monkeypatch.setattr(media_agent, "_call_ai_safe", fake_call_ai)

    upload_resp = await client.post("/api/v1/media/upload", files=_fake_upload())
    mid = upload_resp.json()["id"]

    resp = await client.post(f"/api/v1/media/{mid}/analyze")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "logo" in data["tags"]
    assert data["category"] == "photo"


@pytest.mark.asyncio
async def test_analyze_not_found(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    resp = await client.post("/api/v1/media/99999/analyze")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analyze_fallback_on_ai_failure(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))

    async def failing_ai(*args, **kwargs):
        return json.dumps({"tags": ["unprocessed"], "description": "AI analysis unavailable.", "_fallback": True})

    monkeypatch.setattr(media_agent, "_call_ai_safe", failing_ai)

    upload_resp = await client.post("/api/v1/media/upload", files=_fake_upload())
    mid = upload_resp.json()["id"]

    resp = await client.post(f"/api/v1/media/{mid}/analyze")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "unprocessed" in resp.json()["tags"]


# ── Search ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_media(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))

    # Upload and manually mark as processed with an AI summary
    upload_resp = await client.post(
        "/api/v1/media/upload",
        files=_fake_upload("quarterly-report.pdf", "application/pdf"),
    )
    mid = upload_resp.json()["id"]

    # Patch the media agent to set proper AI tags
    fake_ai_result = json.dumps({
        "tags": ["quarterly", "finance", "report"],
        "description": "Quarterly financial report for Q1 2026",
        "category": "document",
    })
    monkeypatch.setattr(media_agent, "_call_ai_safe", AsyncMock(return_value=fake_ai_result))
    await client.post(f"/api/v1/media/{mid}/analyze")

    resp = await client.get("/api/v1/media/search?q=quarterly")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(d["id"] == mid for d in data)


@pytest.mark.asyncio
async def test_search_no_results(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    resp = await client.get("/api/v1/media/search?q=nonexistentkeyword")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Stats ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_media_stats_empty(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    resp = await client.get("/api/v1/media/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_files"] == 0
    assert data["total_bytes"] == 0


@pytest.mark.asyncio
async def test_media_stats_with_files(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    await client.post("/api/v1/media/upload", files=_fake_upload("a.png", size=1024))
    await client.post("/api/v1/media/upload", files=_fake_upload("b.png", size=2048))

    resp = await client.get("/api/v1/media/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_files"] == 2
    assert data["total_bytes"] == 3072
    assert data["unprocessed_count"] == 2


# ── Report ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_media_report(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))
    await client.post("/api/v1/media/upload", files=_fake_upload("logo.png"))

    resp = await client.get("/api/v1/media/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_files" in data
    assert "type_breakdown" in data
    assert "unlinked_files" in data


# ── Organize ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_organize_media(client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))

    fake_ai_result = json.dumps({
        "entity_type": "employee",
        "reason": "File appears to be an employee headshot",
    })
    monkeypatch.setattr(media_agent, "_call_ai_safe", AsyncMock(return_value=fake_ai_result))

    upload_resp = await client.post("/api/v1/media/upload", files=_fake_upload())
    mid = upload_resp.json()["id"]

    resp = await client.post(f"/api/v1/media/{mid}/organize")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["suggested_entity_type"] == "employee"


# ── Service-Layer Tests (direct, no HTTP) ────────────────────────────


@pytest.mark.asyncio
async def test_service_upload_and_get(db: AsyncSession, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))

    class FakeUpload:
        filename = "direct.png"
        content_type = "image/png"
        async def read(self):
            return b"pixels"

    att = await media_storage.upload_file(db, org_id=1, file=FakeUpload(), user_id=1)
    assert att.id is not None
    assert att.original_name == "direct.png"
    assert att.file_size_bytes == 6

    fetched = await media_storage.get_attachment(db, att.id, org_id=1)
    assert fetched is not None
    assert fetched.original_name == "direct.png"


@pytest.mark.asyncio
async def test_service_soft_delete(db: AsyncSession, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))

    class FakeUpload:
        filename = "delete-me.png"
        content_type = "image/png"
        async def read(self):
            return b"data"

    att = await media_storage.upload_file(db, org_id=1, file=FakeUpload(), user_id=1)
    deleted = await media_storage.soft_delete(db, att.id, org_id=1)
    assert deleted is not None
    assert deleted.is_deleted is True

    # Should not be visible after soft delete
    invisible = await media_storage.get_attachment(db, att.id, org_id=1)
    assert invisible is None


@pytest.mark.asyncio
async def test_service_storage_stats(db: AsyncSession, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))

    class FakeUpload:
        filename = "stats.png"
        content_type = "image/png"
        async def read(self):
            return b"x" * 500

    await media_storage.upload_file(db, org_id=1, file=FakeUpload(), user_id=1)
    stats = await media_storage.get_storage_stats(db, org_id=1)
    assert stats["total_files"] == 1
    assert stats["total_bytes"] == 500
    assert stats["unprocessed_count"] == 1


@pytest.mark.asyncio
async def test_service_validate_mime_rejected(db: AsyncSession, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))

    class FakeUpload:
        filename = "bad.exe"
        content_type = "application/x-msdownload"
        async def read(self):
            return b"payload"

    with pytest.raises(ValueError, match="not allowed"):
        await media_storage.upload_file(db, org_id=1, file=FakeUpload(), user_id=1)


@pytest.mark.asyncio
async def test_service_list_with_entity_filter(db: AsyncSession, tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "UPLOAD_DIR", str(tmp_path))

    class FakeUpload:
        filename = "emp.png"
        content_type = "image/png"
        async def read(self):
            return b"img"

    await media_storage.upload_file(
        db, org_id=1, file=FakeUpload(), user_id=1,
        entity_type="employee", entity_id=42,
    )
    await media_storage.upload_file(
        db, org_id=1, file=FakeUpload(), user_id=1,
        entity_type="project", entity_id=10,
    )

    emp_files = await media_storage.list_attachments(db, org_id=1, entity_type="employee")
    assert len(emp_files) == 1
    assert emp_files[0].entity_id == 42

    all_files = await media_storage.list_attachments(db, org_id=1)
    assert len(all_files) == 2
