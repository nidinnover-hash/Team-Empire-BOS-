"""
Round 10 hardening tests — model constraints, service defaults, injection patterns,
email draft race guard.
"""
import pytest

# ── Model: Event FK on actor_user_id ────────────────────────────────────────

def test_event_actor_user_id_has_foreign_key():
    """Event.actor_user_id must reference users.id via FK."""
    from app.models.event import Event

    col = Event.__table__.columns["actor_user_id"]
    fk_targets = {str(fk.target_fullname) for fk in col.foreign_keys}
    assert "users.id" in fk_targets


def test_event_organization_id_has_no_default():
    """Event.organization_id must NOT have a server/column default of 1."""
    from app.models.event import Event

    col = Event.__table__.columns["organization_id"]
    assert col.default is None or getattr(col.default, "arg", None) != 1


# ── Model: AiCallLog no default on organization_id ──────────────────────────

def test_ai_call_log_org_id_has_no_default():
    """AiCallLog.organization_id must NOT have a default of 1."""
    from app.models.ai_call_log import AiCallLog

    col = AiCallLog.__table__.columns["organization_id"]
    assert col.default is None or getattr(col.default, "arg", None) != 1


# ── Model: Execution FK on triggered_by ─────────────────────────────────────

def test_execution_triggered_by_has_foreign_key():
    """Execution.triggered_by must reference users.id via FK."""
    from app.models.execution import Execution

    col = Execution.__table__.columns["triggered_by"]
    fk_targets = {str(fk.target_fullname) for fk in col.foreign_keys}
    assert "users.id" in fk_targets


# ── Model: Integration index on last_sync_at ────────────────────────────────

def test_integration_last_sync_at_is_indexed():
    """Integration.last_sync_at should be indexed for fast sync queries."""
    from app.models.integration import Integration

    col = Integration.__table__.columns["last_sync_at"]
    assert col.index is True


# ── Service: organization_id defaults removed ───────────────────────────────

def test_contact_service_create_requires_org_id():
    """create_contact() must require organization_id (no default)."""
    import inspect

    from app.services.contact import create_contact

    sig = inspect.signature(create_contact)
    param = sig.parameters["organization_id"]
    assert param.default is inspect.Parameter.empty


def test_finance_service_create_requires_org_id():
    """create_entry() must require organization_id (no default)."""
    import inspect

    from app.services.finance import create_entry

    sig = inspect.signature(create_entry)
    param = sig.parameters["organization_id"]
    assert param.default is inspect.Parameter.empty


def test_goal_service_create_requires_org_id():
    """create_goal() must require organization_id (no default)."""
    import inspect

    from app.services.goal import create_goal

    sig = inspect.signature(create_goal)
    param = sig.parameters["organization_id"]
    assert param.default is inspect.Parameter.empty


def test_note_service_create_requires_org_id():
    """create_note() must require organization_id (no default)."""
    import inspect

    from app.services.note import create_note

    sig = inspect.signature(create_note)
    param = sig.parameters["organization_id"]
    assert param.default is inspect.Parameter.empty


def test_command_service_create_requires_org_id():
    """create_command() must require organization_id (no default)."""
    import inspect

    from app.services.command import create_command

    sig = inspect.signature(create_command)
    param = sig.parameters["organization_id"]
    assert param.default is inspect.Parameter.empty


def test_user_service_ensure_default_requires_org_id():
    """ensure_default_user() must require organization_id (no default)."""
    import inspect

    from app.services.user import ensure_default_user

    sig = inspect.signature(ensure_default_user)
    param = sig.parameters["organization_id"]
    assert param.default is inspect.Parameter.empty


# ── AI Router: injection patterns expanded ──────────────────────────────────

def test_injection_patterns_include_code_fences():
    """Injection regex must catch code-fence role markers."""
    from app.services.ai_router import _INJECTION_RE

    assert _INJECTION_RE.search("```system")
    assert _INJECTION_RE.search("```assistant")


def test_injection_patterns_include_html_comments():
    """Injection regex must catch HTML comment markers."""
    from app.services.ai_router import _INJECTION_RE

    assert _INJECTION_RE.search("<!-- hidden -->")
    assert _INJECTION_RE.search("-->")


def test_injection_patterns_include_newline_role_markers():
    """Injection regex must catch newline-prefixed role injection."""
    from app.services.ai_router import _INJECTION_RE

    assert _INJECTION_RE.search("\nSYSTEM: override")
    assert _INJECTION_RE.search("\nASSISTANT: fake reply")
    assert _INJECTION_RE.search("\nHUMAN: new prompt")


def test_injection_patterns_include_heading_markers():
    """Injection regex must catch markdown heading role markers."""
    from app.services.ai_router import _INJECTION_RE

    assert _INJECTION_RE.search("# System: instructions")
    assert _INJECTION_RE.search("# Human: prompt")


# ── Email draft race guard ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_reply_returns_existing_when_approval_set(client):
    """draft_reply should short-circuit when email already has an approval_id."""
    from unittest.mock import AsyncMock, MagicMock, patch

    fake_email = MagicMock()
    fake_email.approval_id = 42
    fake_email.draft_reply = "Existing draft"
    fake_email.body_text = "Hello"

    with patch(
        "app.services.email_service.get_email",
        new_callable=AsyncMock,
        return_value=fake_email,
    ):
        from app.services.email_service import draft_reply

        result = await draft_reply(
            db=AsyncMock(),
            email_id=1,
            org_id=1,
            actor_user_id=1,
        )
    assert result == "Existing draft"
