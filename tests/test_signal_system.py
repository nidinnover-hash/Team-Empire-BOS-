"""Tests for the BOS signal system MVP."""


import pytest
from pydantic import ValidationError

from app.platform.signals import publish_signal
from app.platform.signals.runtime import get_signal_publisher
from app.platform.signals.schemas import SignalCategory, SignalEnvelope
from app.platform.signals.topics import (
    AI_CALL_COMPLETED,
    AI_CALL_FAILED,
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
    APPROVAL_REQUESTED,
    CONTACT_CREATED,
    CONTACT_DELETED,
    CONTACT_ROUTED,
    CONTACT_UPDATED,
    EXECUTION_COMPLETED,
    FINANCE_INVOICE_CREATED,
    INTEGRATION_CONNECTED,
    INTEGRATION_SYNC_COMPLETED,
    MEMORY_UPDATED,
    SCHEDULER_JOB_COMPLETED,
    SCHEDULER_JOB_FAILED,
    USER_LOGIN,
    WEBHOOK_DELIVERY_FAILED,
    WEBHOOK_DELIVERY_SUCCEEDED,
)


def _make_signal(topic: str = "test.topic", org_id: int = 1, **overrides) -> SignalEnvelope:
    defaults = dict(
        topic=topic,
        category=SignalCategory.SYSTEM,
        organization_id=org_id,
        source="test",
    )
    defaults.update(overrides)
    return SignalEnvelope(**defaults)


# ---------------------------------------------------------------------------
# SignalEnvelope
# ---------------------------------------------------------------------------


class TestSignalEnvelope:
    def test_creates_with_defaults(self):
        sig = _make_signal()
        assert sig.signal_id
        assert sig.occurred_at is not None
        assert sig.payload == {}
        assert sig.metadata == {}

    def test_is_frozen(self):
        sig = _make_signal()
        with pytest.raises(ValidationError):
            sig.topic = "changed"

    def test_custom_payload(self):
        sig = _make_signal(payload={"key": "value"})
        assert sig.payload == {"key": "value"}

    def test_correlation_and_causation(self):
        sig = _make_signal(correlation_id="corr-1", causation_id="cause-1")
        assert sig.correlation_id == "corr-1"
        assert sig.causation_id == "cause-1"


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


class TestTopics:
    def test_all_topics_are_dotted_strings(self):
        topics = [
            APPROVAL_REQUESTED, APPROVAL_APPROVED,
            EXECUTION_COMPLETED,
            WEBHOOK_DELIVERY_SUCCEEDED,
            SCHEDULER_JOB_COMPLETED,
            AI_CALL_COMPLETED,
            CONTACT_CREATED, CONTACT_UPDATED, CONTACT_DELETED, CONTACT_ROUTED,
            FINANCE_INVOICE_CREATED,
            INTEGRATION_CONNECTED, INTEGRATION_SYNC_COMPLETED,
            MEMORY_UPDATED,
            USER_LOGIN,
        ]
        for t in topics:
            assert isinstance(t, str)
            assert "." in t, f"Topic {t!r} should use dotted notation"


# ---------------------------------------------------------------------------
# InMemorySignalStore
# ---------------------------------------------------------------------------


class TestInMemoryStore:
    @pytest.mark.asyncio
    async def test_append_and_list(self):
        from app.platform.signals.store import InMemorySignalStore

        store = InMemorySignalStore()
        sig = _make_signal(topic="store.test")
        result = await store.append(sig)
        assert result.signal_id == sig.signal_id

        recent = await store.list_recent(organization_id=1)
        assert len(recent) == 1
        assert recent[0].topic == "store.test"

    @pytest.mark.asyncio
    async def test_filters_by_org(self):
        from app.platform.signals.store import InMemorySignalStore

        store = InMemorySignalStore()
        await store.append(_make_signal(org_id=1))
        await store.append(_make_signal(org_id=2))

        org1 = await store.list_recent(organization_id=1)
        assert len(org1) == 1

    @pytest.mark.asyncio
    async def test_filters_by_topic(self):
        from app.platform.signals.store import InMemorySignalStore

        store = InMemorySignalStore()
        await store.append(_make_signal(topic="a.b"))
        await store.append(_make_signal(topic="c.d"))

        filtered = await store.list_recent(topic="a.b")
        assert len(filtered) == 1
        assert filtered[0].topic == "a.b"

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        from app.platform.signals.store import InMemorySignalStore

        store = InMemorySignalStore()
        for _ in range(10):
            await store.append(_make_signal())

        limited = await store.list_recent(limit=3)
        assert len(limited) == 3


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------


class TestPublisher:
    @pytest.mark.asyncio
    async def test_publish_invokes_typed_handler(self):
        from app.platform.signals.publisher import InProcessSignalPublisher
        from app.platform.signals.store import InMemorySignalStore

        store = InMemorySignalStore()
        pub = InProcessSignalPublisher(store)

        received = []
        pub.subscribe("test.topic", lambda s: _async_append(received, s))

        sig = _make_signal(topic="test.topic")
        await pub.publish(sig)
        assert len(received) == 1
        assert received[0].signal_id == sig.signal_id

    @pytest.mark.asyncio
    async def test_publish_invokes_global_handler(self):
        from app.platform.signals.publisher import InProcessSignalPublisher
        from app.platform.signals.store import InMemorySignalStore

        store = InMemorySignalStore()
        pub = InProcessSignalPublisher(store)

        received = []
        pub.subscribe_all(lambda s: _async_append(received, s))

        await pub.publish(_make_signal(topic="any.topic"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_handler_error_does_not_propagate(self):
        from app.platform.signals.publisher import InProcessSignalPublisher
        from app.platform.signals.store import InMemorySignalStore

        store = InMemorySignalStore()
        pub = InProcessSignalPublisher(store)

        async def failing_handler(s):
            raise RuntimeError("boom")

        pub.subscribe_all(failing_handler)
        # Should NOT raise
        await pub.publish(_make_signal())

    @pytest.mark.asyncio
    async def test_no_duplicate_subscriptions(self):
        from app.platform.signals.publisher import InProcessSignalPublisher
        from app.platform.signals.store import InMemorySignalStore

        store = InMemorySignalStore()
        pub = InProcessSignalPublisher(store)

        received = []

        async def handler(s):
            received.append(s)

        pub.subscribe("x.y", handler)
        pub.subscribe("x.y", handler)  # duplicate — should be ignored

        await pub.publish(_make_signal(topic="x.y"))
        assert len(received) == 1


# ---------------------------------------------------------------------------
# publish_signal (top-level)
# ---------------------------------------------------------------------------


class TestPublishSignal:
    @pytest.mark.asyncio
    async def test_publish_without_db(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "SIGNAL_SYSTEM_ENABLED", True)
        sig = _make_signal(topic="test.integration")
        result = await publish_signal(sig)
        assert result.signal_id == sig.signal_id

    @pytest.mark.asyncio
    async def test_disabled_returns_signal_without_publishing(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "SIGNAL_SYSTEM_ENABLED", False)

        received = []
        publisher = get_signal_publisher()
        publisher.subscribe_all(lambda s: _async_append(received, s))

        sig = _make_signal(topic="should.not.publish")
        result = await publish_signal(sig)
        assert result.signal_id == sig.signal_id
        assert len(received) == 0


# ---------------------------------------------------------------------------
# Consumers
# ---------------------------------------------------------------------------


class TestConsumers:
    def test_register_default_consumers_is_idempotent(self, monkeypatch):
        from app.core.config import settings
        from app.platform.signals import consumers
        monkeypatch.setattr(consumers, "_registered", False)
        monkeypatch.setattr(settings, "SIGNAL_SYSTEM_ENABLED", True)

        consumers.register_default_consumers()
        consumers.register_default_consumers()  # second call is no-op
        assert consumers._registered is True

    @pytest.mark.asyncio
    async def test_metrics_counter_consumer(self):
        from app.platform.signals.consumers import _metrics_counter_consumer, _signal_counts

        _signal_counts.clear()
        sig = _make_signal(topic="counter.test")
        await _metrics_counter_consumer(sig)
        await _metrics_counter_consumer(sig)

        from app.platform.signals.consumers import get_signal_counts
        counts = get_signal_counts()
        assert counts["counter.test"] == 2


# ---------------------------------------------------------------------------
# Approval signal wiring
# ---------------------------------------------------------------------------


class TestApprovalSignalWiring:
    @pytest.mark.asyncio
    async def test_publish_approval_signal_accepts_db(self):
        """_publish_approval_signal should accept db keyword arg without NameError."""
        from unittest.mock import MagicMock

        from app.services.approval import _publish_approval_signal

        mock_approval = MagicMock()
        mock_approval.organization_id = 1
        mock_approval.id = 42
        mock_approval.approval_type = "send_message"
        mock_approval.status = "pending"
        mock_approval.requested_by = 1
        mock_approval.approved_by = None
        mock_approval.approved_at = None
        mock_approval.expires_at = None

        # Should not raise NameError for db
        await _publish_approval_signal(
            APPROVAL_REQUESTED,
            mock_approval,
            actor_user_id=1,
            db=None,
        )

    @pytest.mark.asyncio
    async def test_request_approval_emits_requested_signal(self, db, monkeypatch):
        from app.schemas.approval import ApprovalRequestCreate
        from app.services import approval as approval_service

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        async def fake_notification(*args, **kwargs):
            return None

        monkeypatch.setattr(approval_service, "publish_signal", fake_publish)
        monkeypatch.setattr(approval_service, "create_notification", fake_notification)

        approval = await approval_service.request_approval(
            db,
            requested_by=1,
            data=ApprovalRequestCreate(
                organization_id=1,
                approval_type="send_message",
                payload_json={"email_id": 123},
            ),
        )

        assert approval.status == "pending"
        assert len(published) == 1
        signal = published[0]
        assert signal.topic == APPROVAL_REQUESTED
        assert signal.entity_type == "approval"
        assert signal.entity_id == str(approval.id)
        assert signal.payload["approval_type"] == "send_message"
        assert signal.payload["status"] == "pending"

    @pytest.mark.asyncio
    async def test_approve_approval_emits_approved_signal(self, db, monkeypatch):
        from app.models.approval import Approval
        from app.services import approval as approval_service

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        async def fake_notification(*args, **kwargs):
            return None

        monkeypatch.setattr(approval_service, "publish_signal", fake_publish)
        monkeypatch.setattr(approval_service, "create_notification", fake_notification)

        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="assign_task",
            payload_json={"task_id": 7},
            status="pending",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        updated = await approval_service.approve_approval(
            db,
            approval_id=approval.id,
            approver_id=1,
            organization_id=1,
        )

        assert updated is not None
        assert updated.status == "approved"
        assert len(published) == 1
        signal = published[0]
        assert signal.topic == APPROVAL_APPROVED
        assert signal.entity_id == str(approval.id)
        assert signal.payload["status"] == "approved"
        assert signal.payload["approved_by"] == 1

    @pytest.mark.asyncio
    async def test_reject_approval_emits_rejected_signal(self, db, monkeypatch):
        from app.models.approval import Approval
        from app.services import approval as approval_service

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        async def fake_notification(*args, **kwargs):
            return None

        monkeypatch.setattr(approval_service, "publish_signal", fake_publish)
        monkeypatch.setattr(approval_service, "create_notification", fake_notification)

        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="spend_money",
            payload_json={"amount": 25},
            status="pending",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        updated = await approval_service.reject_approval(
            db,
            approval_id=approval.id,
            approver_id=1,
            organization_id=1,
        )

        assert updated is not None
        assert updated.status == "rejected"
        assert len(published) == 1
        signal = published[0]
        assert signal.topic == APPROVAL_REJECTED
        assert signal.entity_id == str(approval.id)
        assert signal.payload["status"] == "rejected"


class TestExecutionSignalWiring:
    @pytest.mark.asyncio
    async def test_create_execution_emits_started_signal(self, db, monkeypatch):
        from app.services import execution as execution_service

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        monkeypatch.setattr(execution_service, "publish_signal", fake_publish)

        execution, created = await execution_service.create_execution(
            db,
            organization_id=1,
            approval_id=500,
            triggered_by=1,
            execute_idempotency_key="exec-start-1",
        )

        assert created is True
        assert execution.status == "running"
        assert len(published) == 1
        signal = published[0]
        assert signal.topic == "execution.started"
        assert signal.entity_type == "execution"
        assert signal.entity_id == str(execution.id)
        assert signal.payload["approval_id"] == 500

    @pytest.mark.asyncio
    async def test_complete_execution_emits_completed_signal(self, db, monkeypatch):
        from app.services import execution as execution_service

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        monkeypatch.setattr(execution_service, "publish_signal", fake_publish)

        execution, created = await execution_service.create_execution(
            db,
            organization_id=1,
            approval_id=501,
            triggered_by=1,
            execute_idempotency_key="exec-complete-1",
        )
        assert created is True
        published.clear()

        completed = await execution_service.complete_execution(
            db,
            execution_id=execution.id,
            organization_id=1,
            status="succeeded",
            output_json={"ok": True},
        )

        assert completed is not None
        assert completed.status == "succeeded"
        assert len(published) == 1
        signal = published[0]
        assert signal.topic == EXECUTION_COMPLETED
        assert signal.entity_id == str(execution.id)
        assert signal.payload["status"] == "succeeded"
        assert signal.payload["output"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_complete_execution_emits_failed_signal(self, db, monkeypatch):
        from app.services import execution as execution_service

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        monkeypatch.setattr(execution_service, "publish_signal", fake_publish)

        execution, created = await execution_service.create_execution(
            db,
            organization_id=1,
            approval_id=502,
            triggered_by=1,
            execute_idempotency_key="exec-failed-1",
        )
        assert created is True
        published.clear()

        completed = await execution_service.complete_execution(
            db,
            execution_id=execution.id,
            organization_id=1,
            status="failed",
            error_text="boom",
        )

        assert completed is not None
        assert completed.status == "failed"
        assert len(published) == 1
        signal = published[0]
        assert signal.topic == "execution.failed"
        assert signal.entity_id == str(execution.id)
        assert signal.payload["status"] == "failed"
        assert signal.payload["error_text"] == "boom"


class TestWebhookSignalWiring:
    @pytest.mark.asyncio
    async def test_publish_webhook_delivery_signal_success(self, db, monkeypatch):
        from app.models.webhook import WebhookDelivery
        from app.services import webhook as webhook_service

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        monkeypatch.setattr(webhook_service, "publish_signal", fake_publish)

        delivery = WebhookDelivery(
            webhook_endpoint_id=10,
            organization_id=1,
            event="approval.approved",
            payload_json={"approval_id": 42},
            status="success",
            response_status_code=200,
            duration_ms=87,
            attempt_count=1,
            max_retries=5,
        )
        delivery.id = 77

        await webhook_service._publish_webhook_delivery_signal(
            db,
            delivery,
            source="webhook.dispatch",
        )

        assert len(published) == 1
        signal = published[0]
        assert signal.topic == WEBHOOK_DELIVERY_SUCCEEDED
        assert signal.entity_type == "webhook_delivery"
        assert signal.entity_id == "77"
        assert signal.payload["delivery_id"] == 77
        assert signal.payload["status"] == "success"

    @pytest.mark.asyncio
    async def test_publish_webhook_delivery_signal_failure(self, db, monkeypatch):
        from app.models.webhook import WebhookDelivery
        from app.services import webhook as webhook_service

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        monkeypatch.setattr(webhook_service, "publish_signal", fake_publish)

        delivery = WebhookDelivery(
            webhook_endpoint_id=11,
            organization_id=1,
            event="approval.rejected",
            payload_json={"approval_id": 84},
            status="failed",
            error_message="HTTP 500",
            response_status_code=500,
            duration_ms=125,
            attempt_count=3,
            max_retries=5,
        )
        delivery.id = 88

        await webhook_service._publish_webhook_delivery_signal(
            db,
            delivery,
            source="webhook.retry",
        )

        assert len(published) == 1
        signal = published[0]
        assert signal.topic == WEBHOOK_DELIVERY_FAILED
        assert signal.entity_id == "88"
        assert signal.payload["status"] == "failed"
        assert signal.payload["error_message"] == "HTTP 500"


class TestAiRouterSignalWiring:
    @pytest.mark.asyncio
    async def test_log_ai_call_emits_completed_signal(self, db, monkeypatch):
        from app.engines.brain import router as brain_router

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        monkeypatch.setattr(brain_router, "publish_signal", fake_publish)

        await brain_router._log_ai_call(
            provider="openai",
            model_name="gpt-4o-mini",
            latency_ms=140,
            input_tokens=20,
            output_tokens=8,
            used_fallback=False,
            error_type=None,
            prompt_type="chat",
            organization_id=1,
            request_id="req-ai-ok",
            db=db,
        )

        assert len(published) == 1
        signal = published[0]
        assert signal.topic == AI_CALL_COMPLETED
        assert signal.entity_type == "ai_call"
        assert signal.entity_id == "req-ai-ok"
        assert signal.correlation_id == "req-ai-ok"
        assert signal.payload["provider"] == "openai"
        assert signal.payload["error_type"] is None

    @pytest.mark.asyncio
    async def test_log_ai_call_emits_failed_signal(self, db, monkeypatch):
        from app.engines.brain import router as brain_router

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        monkeypatch.setattr(brain_router, "publish_signal", fake_publish)

        await brain_router._log_ai_call(
            provider="groq",
            model_name="llama-3.3-70b-versatile",
            latency_ms=900,
            input_tokens=None,
            output_tokens=None,
            used_fallback=True,
            fallback_from="openai",
            error_type="RateLimitError",
            prompt_type="intent",
            organization_id=1,
            request_id="req-ai-failed",
            db=db,
        )

        assert len(published) == 1
        signal = published[0]
        assert signal.topic == AI_CALL_FAILED
        assert signal.entity_id == "req-ai-failed"
        assert signal.payload["provider"] == "groq"
        assert signal.payload["fallback_from"] == "openai"
        assert signal.payload["error_type"] == "RateLimitError"


class TestSchedulerSignalWiring:
    @pytest.mark.asyncio
    async def test_record_job_run_emits_completed_signal(self, db, monkeypatch):
        from datetime import UTC, datetime, timedelta

        from app.jobs import _helpers as scheduler_helpers

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        monkeypatch.setattr(scheduler_helpers, "publish_signal", fake_publish)

        started_at = datetime(2026, 3, 7, 10, 0, tzinfo=UTC)
        finished_at = started_at + timedelta(seconds=3, milliseconds=250)

        await scheduler_helpers.record_job_run(
            db,
            org_id=1,
            job_name="nightly_sync",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            details={"integrations": 4},
        )

        assert len(published) == 1
        signal = published[0]
        assert signal.topic == SCHEDULER_JOB_COMPLETED
        assert signal.entity_type == "scheduler_job"
        assert signal.entity_id == "nightly_sync"
        assert signal.summary_text == "nightly_sync:ok"
        assert signal.payload["job_name"] == "nightly_sync"
        assert signal.payload["status"] == "ok"
        assert signal.payload["duration_ms"] == 3250
        assert signal.payload["details"] == {"integrations": 4}
        assert signal.payload["error"] is None

    @pytest.mark.asyncio
    async def test_record_job_run_emits_failed_signal(self, db, monkeypatch):
        from datetime import UTC, datetime, timedelta

        from app.jobs import _helpers as scheduler_helpers

        published = []

        async def fake_publish(signal, *, db=None):
            published.append(signal)
            return signal

        monkeypatch.setattr(scheduler_helpers, "publish_signal", fake_publish)

        started_at = datetime(2026, 3, 7, 11, 0, tzinfo=UTC)
        finished_at = started_at + timedelta(milliseconds=800)

        await scheduler_helpers.record_job_run(
            db,
            org_id=1,
            job_name="retry_webhooks",
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            details={"attempted": 6},
            error="network timeout",
        )

        assert len(published) == 1
        signal = published[0]
        assert signal.topic == SCHEDULER_JOB_FAILED
        assert signal.entity_type == "scheduler_job"
        assert signal.entity_id == "retry_webhooks"
        assert signal.summary_text == "retry_webhooks:error"
        assert signal.payload["job_name"] == "retry_webhooks"
        assert signal.payload["status"] == "error"
        assert signal.payload["duration_ms"] == 800
        assert signal.payload["details"] == {"attempted": 6}
        assert signal.payload["error"] == "network timeout"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_append(lst, item):
    lst.append(item)
