"""Tests for the BOS decision abstraction layer."""

import pytest
from pydantic import ValidationError

from app.platform.decisions import (
    DECISION_APPROVAL_AUTO,
    DECISION_CONTACT_ROUTE,
    DECISION_EMAIL_DRAFT,
    DECISION_ESCALATION,
    DECISION_LEAD_SCORE,
    DECISION_TASK_SUGGEST,
    DecisionEnvelope,
    DecisionOutcome,
)


class TestDecisionEnvelope:
    def test_creates_with_defaults(self):
        env = DecisionEnvelope(
            decision_type="test.decision",
            outcome=DecisionOutcome.SUGGESTED,
            confidence=0.85,
            organization_id=1,
        )
        assert env.decision_id
        assert env.outcome == DecisionOutcome.SUGGESTED
        assert env.confidence == 0.85
        assert env.signal_ids == []
        assert env.metadata == {}

    def test_is_frozen(self):
        env = DecisionEnvelope(
            decision_type="test", outcome=DecisionOutcome.APPROVED,
            confidence=0.9, organization_id=1,
        )
        with pytest.raises(ValidationError):
            env.outcome = DecisionOutcome.REJECTED

    def test_all_outcomes(self):
        for outcome in DecisionOutcome:
            env = DecisionEnvelope(
                decision_type="test", outcome=outcome,
                confidence=0.5, organization_id=1,
            )
            assert env.outcome == outcome


class TestDecisionOutcome:
    def test_values(self):
        assert DecisionOutcome.APPROVED == "approved"
        assert DecisionOutcome.REJECTED == "rejected"
        assert DecisionOutcome.SUGGESTED == "suggested"
        assert DecisionOutcome.DEFERRED == "deferred"
        assert DecisionOutcome.ESCALATED == "escalated"


class TestDecisionTypes:
    def test_all_types_are_dotted_or_simple_strings(self):
        types = [
            DECISION_CONTACT_ROUTE, DECISION_LEAD_SCORE,
            DECISION_EMAIL_DRAFT, DECISION_TASK_SUGGEST,
            DECISION_APPROVAL_AUTO, DECISION_ESCALATION,
        ]
        for t in types:
            assert isinstance(t, str)
            assert len(t) > 0


class TestRecordDecision:
    @pytest.mark.asyncio
    async def test_record_decision_persists_and_returns_envelope(self, db):
        from app.platform.decisions import record_decision

        env = await record_decision(
            db,
            decision_type=DECISION_CONTACT_ROUTE,
            outcome=DecisionOutcome.SUGGESTED,
            confidence=0.75,
            organization_id=1,
            reasoning="Lead score above threshold",
            entity_type="contact",
            entity_id="42",
        )
        assert isinstance(env, DecisionEnvelope)
        assert env.decision_type == DECISION_CONTACT_ROUTE
        assert env.outcome == DecisionOutcome.SUGGESTED
        assert env.confidence == 0.75
        assert env.trace_id is not None
        assert env.entity_type == "contact"
        assert env.entity_id == "42"

    @pytest.mark.asyncio
    async def test_record_decision_creates_trace_row(self, db):
        from sqlalchemy import select

        from app.models.decision_trace import DecisionTrace
        from app.platform.decisions import record_decision

        env = await record_decision(
            db,
            decision_type=DECISION_LEAD_SCORE,
            outcome=DecisionOutcome.APPROVED,
            confidence=0.92,
            organization_id=1,
            reasoning="High-value lead",
        )
        result = await db.execute(
            select(DecisionTrace).where(DecisionTrace.id == env.trace_id)
        )
        trace = result.scalar_one()
        assert trace.trace_type == DECISION_LEAD_SCORE
        assert trace.confidence_score == 0.92
        assert "High-value lead" in trace.summary

    @pytest.mark.asyncio
    async def test_record_decision_with_signal_ids(self, db):
        from app.platform.decisions import record_decision

        env = await record_decision(
            db,
            decision_type=DECISION_ESCALATION,
            outcome=DecisionOutcome.ESCALATED,
            confidence=0.6,
            organization_id=1,
            signal_ids=["sig-1", "sig-2"],
        )
        assert env.signal_ids == ["sig-1", "sig-2"]
