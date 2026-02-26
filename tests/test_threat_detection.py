"""Tests for app/services/data_collection/threats.py — threat detection and training."""
from datetime import UTC, datetime

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.note import Note
from app.schemas.data_collection import ThreatTrainRequest
from app.services.data_collection.threats import (
    _scan_text_for_threats,
    detect_threats,
    get_threat_layer_report,
    train_threat_signals,
)


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


# ── _scan_text_for_threats (pure function) ────────────────────────────────────


async def test_scan_detects_credential_leak():
    results = _scan_text_for_threats("My password is hunter2")
    categories = [r["category"] for r in results]
    assert "credential_leak" in categories


async def test_scan_detects_injection_attempt():
    results = _scan_text_for_threats("input was ' or 1=1 --")
    categories = [r["category"] for r in results]
    assert "injection_attempt" in categories


async def test_scan_detects_config_weakness():
    results = _scan_text_for_threats("debug=true in production config")
    categories = [r["category"] for r in results]
    assert "config_weakness" in categories


async def test_scan_detects_dependency_risk():
    results = _scan_text_for_threats("CVE-2024-1234 found in package")
    categories = [r["category"] for r in results]
    assert "dependency_risk" in categories


async def test_scan_clean_text_returns_empty():
    results = _scan_text_for_threats("Today we had a great team meeting about Q3 goals.")
    assert results == []


async def test_scan_case_insensitive():
    results = _scan_text_for_threats("DROP TABLE users;")
    categories = [r["category"] for r in results]
    assert "injection_attempt" in categories


# ── detect_threats (needs DB) ─────────────────────────────────────────────────


async def test_detect_threats_empty_db(client):
    """Detection with no data returns zero signals."""
    session, agen = await _get_session()
    try:
        result = await detect_threats(session, org_id=1)
        assert result.signals_found == 0
        assert result.signals == []
    finally:
        await agen.aclose()


async def test_detect_threats_from_note(client):
    """Detection finds threats in notes."""
    session, agen = await _get_session()
    try:
        note = Note(
            organization_id=1,
            title="Security Issue",
            content="Found password leak in the api_key config file",
            created_at=datetime.now(UTC),
        )
        session.add(note)
        await session.commit()

        result = await detect_threats(session, org_id=1)
        assert result.signals_found >= 1
        categories = [s.category for s in result.signals]
        assert "credential_leak" in categories
    finally:
        await agen.aclose()


async def test_detect_threats_creates_policy_for_critical(client):
    """Critical/high severity threats generate policy drafts."""
    session, agen = await _get_session()
    try:
        note = Note(
            organization_id=1,
            title="Injection",
            content="User sent ' or 1=1 in the login form",
            created_at=datetime.now(UTC),
        )
        session.add(note)
        await session.commit()

        result = await detect_threats(session, org_id=1)
        assert result.policy_drafts_created >= 1
    finally:
        await agen.aclose()


async def test_detect_threats_deduplicates(client):
    """Same threat category + source should not be counted twice."""
    session, agen = await _get_session()
    try:
        note = Note(
            organization_id=1,
            title="password password password",
            content="secret token api_key",
            created_at=datetime.now(UTC),
        )
        session.add(note)
        await session.commit()

        result = await detect_threats(session, org_id=1)
        # Should only have one credential_leak per source, not multiple
        cred_signals = [s for s in result.signals if s.category == "credential_leak"]
        assert len(cred_signals) == 1
    finally:
        await agen.aclose()


# ── train_threat_signals ──────────────────────────────────────────────────────


async def test_train_approve_activates_policy(client):
    """Approving a signal activates its associated policy."""
    session, agen = await _get_session()
    try:
        # First create some signals via detect_threats
        note = Note(
            organization_id=1,
            title="Critical password leak",
            content="api_key exposed in production logs",
            created_at=datetime.now(UTC),
        )
        session.add(note)
        await session.commit()

        detection = await detect_threats(session, org_id=1)
        signal_ids = [s.id for s in detection.signals]
        assert len(signal_ids) >= 1

        result = await train_threat_signals(
            session,
            org_id=1,
            data=ThreatTrainRequest(signal_ids=signal_ids, action="approve"),
        )
        assert result.processed >= 1
        assert len(result.memory_keys) >= 1
    finally:
        await agen.aclose()


async def test_train_dismiss_deactivates_policy(client):
    """Dismissing a signal deactivates its policy."""
    session, agen = await _get_session()
    try:
        note = Note(
            organization_id=1,
            title="Injection found",
            content="Someone tried ' or 1=1 against the api",
            created_at=datetime.now(UTC),
        )
        session.add(note)
        await session.commit()

        detection = await detect_threats(session, org_id=1)
        signal_ids = [s.id for s in detection.signals]

        result = await train_threat_signals(
            session,
            org_id=1,
            data=ThreatTrainRequest(signal_ids=signal_ids, action="dismiss"),
        )
        assert result.processed >= 1
    finally:
        await agen.aclose()


async def test_train_no_matching_signals_raises(client):
    """Training with non-existent signal IDs raises ValueError."""
    session, agen = await _get_session()
    try:
        import pytest
        with pytest.raises(ValueError, match="No matching"):
            await train_threat_signals(
                session,
                org_id=1,
                data=ThreatTrainRequest(signal_ids=[99999], action="approve"),
            )
    finally:
        await agen.aclose()


# ── get_threat_layer_report ───────────────────────────────────────────────────


async def test_threat_layer_report_structure(client):
    """Report has all required fields."""
    session, agen = await _get_session()
    try:
        report = await get_threat_layer_report(session, org_id=1)
        assert 0 <= report.security_score <= 100
        assert isinstance(report.severity_breakdown, dict)
        assert isinstance(report.recommendations, list)
        assert len(report.recommendations) >= 1
    finally:
        await agen.aclose()


async def test_threat_layer_report_with_signals(client):
    """Report reflects recent threat signals."""
    session, agen = await _get_session()
    try:
        note = Note(
            organization_id=1,
            title="Password leak found",
            content="credential exposure in admin panel",
            created_at=datetime.now(UTC),
        )
        session.add(note)
        await session.commit()
        await detect_threats(session, org_id=1)

        report = await get_threat_layer_report(session, org_id=1)
        assert report.total_signals_7d >= 1
        assert report.security_score < 100
    finally:
        await agen.aclose()
