"""Tests for photo character study and digital threat detection features."""


# ── Photo Character Study ──────────────────────────────────────────────────────

async def test_photo_character_upload_with_mocked_ocr(client, monkeypatch):
    from app.services import data_collection as dc_svc

    def _fake_ocr(_payload: bytes) -> tuple[str, str]:
        return (
            "Meeting roadmap strategy plan with team. Decision confirmed. "
            "Goal achieved by deadline. Data metrics analysis report dashboard kpi. "
            "Support help and understand the concern. Design brainstorm innovate concept.",
            "mock-ocr",
        )

    monkeypatch.setattr(dc_svc, "extract_text_from_image_bytes", _fake_ocr)

    r = await client.post(
        "/api/v1/data/photo-character/upload-analyze",
        files={"file": ("portrait.png", b"fake-image-bytes", "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "portrait.png"
    assert body["ocr_engine"] == "mock-ocr"
    assert body["extracted_chars"] > 50
    assert len(body["traits"]) >= 2
    assert body["confidence"] in ("low", "medium", "high")
    assert body["memory_keys"]
    assert body["note_id"] is not None
    assert "character study" in body["message"].lower()


async def test_photo_character_empty_file_rejected(client, monkeypatch):
    r = await client.post(
        "/api/v1/data/photo-character/upload-analyze",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


async def test_photo_character_traits_extraction():
    from app.services.data_collection import _extract_character_traits

    text = "data analysis metrics report dashboard kpi measure"
    traits = _extract_character_traits(text)
    assert "analytical" in traits

    text2 = "decision confirm approve execute action done"
    traits2 = _extract_character_traits(text2)
    assert "decisive" in traits2


async def test_photo_character_confidence_levels():
    from app.services.data_collection import _character_confidence

    assert _character_confidence(["a", "b", "c", "d"], 300) == "high"
    assert _character_confidence(["a", "b"], 100) == "medium"
    assert _character_confidence(["a"], 30) == "low"
    assert _character_confidence([], 0) == "low"


# ── Digital Threat Detection ───────────────────────────────────────────────────

async def test_threat_detection_scan_clean_org(client):
    r = await client.post("/api/v1/data/threats/detect")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "full_scan"
    assert body["signals_found"] >= 0
    assert isinstance(body["signals"], list)
    assert isinstance(body["severity_breakdown"], dict)
    assert "message" in body


async def test_threat_detection_finds_credential_pattern(client):
    # Inject a note with credential-like content
    r = await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "notes",
            "content": "Found password leak and api_key exposed in logs",
            "split_lines": False,
        },
    )
    assert r.status_code == 200

    # Now detect threats
    r = await client.post("/api/v1/data/threats/detect")
    assert r.status_code == 200
    body = r.json()
    assert body["signals_found"] >= 1
    categories = [s["category"] for s in body["signals"]]
    assert "credential_leak" in categories
    severities = [s["severity"] for s in body["signals"]]
    assert "critical" in severities


async def test_threat_detection_finds_injection_pattern(client):
    r = await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "notes",
            "content": "User input contained ' or 1=1 and <script alert pattern",
            "split_lines": False,
        },
    )
    assert r.status_code == 200

    r = await client.post("/api/v1/data/threats/detect")
    assert r.status_code == 200
    body = r.json()
    categories = [s["category"] for s in body["signals"]]
    assert "injection_attempt" in categories


async def test_threat_train_approve_activates_policy(client):
    # Inject threatening content and detect
    await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "notes",
            "content": "Critical password exposure and secret token leaked",
            "split_lines": False,
        },
    )
    detect_r = await client.post("/api/v1/data/threats/detect")
    assert detect_r.status_code == 200
    signals = detect_r.json()["signals"]
    assert len(signals) >= 1

    signal_ids = [s["id"] for s in signals[:3]]
    train_r = await client.post(
        "/api/v1/data/threats/train",
        json={"signal_ids": signal_ids, "action": "approve"},
    )
    assert train_r.status_code == 200
    body = train_r.json()
    assert body["processed"] >= 1
    assert body["policies_activated"] >= 0
    assert body["memory_keys"]
    assert "security intelligence updated" in body["message"].lower()


async def test_threat_train_dismiss(client):
    await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "notes",
            "content": "The word password was used in a safe educational context",
            "split_lines": False,
        },
    )
    detect_r = await client.post("/api/v1/data/threats/detect")
    signals = detect_r.json()["signals"]
    if signals:
        signal_ids = [s["id"] for s in signals[:2]]
        train_r = await client.post(
            "/api/v1/data/threats/train",
            json={"signal_ids": signal_ids, "action": "dismiss"},
        )
        assert train_r.status_code == 200
        body = train_r.json()
        assert body["processed"] >= 1
        assert body["policies_dismissed"] >= 0


async def test_threat_train_invalid_ids(client):
    r = await client.post(
        "/api/v1/data/threats/train",
        json={"signal_ids": [99999], "action": "approve"},
    )
    assert r.status_code == 400
    assert "no matching" in r.json()["detail"].lower()


async def test_threat_layer_report(client):
    r = await client.get("/api/v1/data/threats/layer")
    assert r.status_code == 200
    body = r.json()
    assert "security_score" in body
    assert 0 <= body["security_score"] <= 100
    assert "total_signals_7d" in body
    assert isinstance(body["severity_breakdown"], dict)
    assert isinstance(body["top_threats"], list)
    assert "active_policies" in body
    assert "auto_mitigated_count" in body
    assert isinstance(body["recommendations"], list)


async def test_threat_layer_via_layers_endpoint(client):
    r = await client.get("/api/v1/layers/threat-detection")
    assert r.status_code == 200
    body = r.json()
    assert "security_score" in body
    assert 0 <= body["security_score"] <= 100


async def test_threat_scan_creates_policy_drafts_for_critical(client):
    await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "notes",
            "content": "Leaked credentials and private_key found in public repo",
            "split_lines": False,
        },
    )
    r = await client.post("/api/v1/data/threats/detect")
    assert r.status_code == 200
    body = r.json()
    assert body["policy_drafts_created"] >= 1


async def test_threat_detection_requires_admin(client):
    """STAFF role should be denied for threat detection."""
    from app.core.security import create_access_token
    staff_token = create_access_token(
        {"id": 4, "email": "staff@org1.com", "role": "STAFF", "org_id": 1, "token_version": 1}
    )
    r = await client.post(
        "/api/v1/data/threats/detect",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert r.status_code == 403


# ── Threat pattern scan utility ────────────────────────────────────────────────

async def test_scan_text_for_threats_utility():
    from app.services.data_collection import _scan_text_for_threats

    result = _scan_text_for_threats("password api_key secret token")
    assert len(result) >= 1
    assert result[0]["category"] == "credential_leak"

    result2 = _scan_text_for_threats("normal business content about meetings")
    assert len(result2) == 0

    result3 = _scan_text_for_threats("eval( and <script injection")
    assert any(r["category"] == "injection_attempt" for r in result3)
