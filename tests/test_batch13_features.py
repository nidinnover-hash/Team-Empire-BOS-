"""Tests for batch 13 features."""
import pytest

from app.services import (
    email_sequence as es_svc,
    deal_risk as dr_svc,
    contact_relationship as cr_svc,
    pipeline_snapshot as ps_svc,
    user_activity_heatmap as ua_svc,
    document_template as dt_svc,
    goal_cascade as gc_svc,
)


def _obj(**kw):
    """Create a simple namespace object from keyword args."""
    class _O: pass
    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


TS = "2026-03-10T00:00:00+00:00"


# ── Email Sequences ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_email_sequence(client, monkeypatch):
    async def fake(db, *, organization_id, name, trigger_event, description=None, exit_condition=None, created_by_user_id=None):
        return _obj(id=1, organization_id=1, name=name, description=description,
                     trigger_event=trigger_event, exit_condition=exit_condition,
                     is_active=True, total_enrolled=0, total_completed=0,
                     created_by_user_id=created_by_user_id, created_at=TS)
    monkeypatch.setattr(es_svc, "create_sequence", fake)
    r = await client.post("/api/v1/email-sequences", json={"name": "Welcome", "trigger_event": "contact.created"})
    assert r.status_code == 201
    assert r.json()["name"] == "Welcome"


@pytest.mark.asyncio
async def test_list_email_sequences(client, monkeypatch):
    async def fake(db, org_id, *, is_active=None): return []
    monkeypatch.setattr(es_svc, "list_sequences", fake)
    r = await client.get("/api/v1/email-sequences")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_email_sequence_stats(client, monkeypatch):
    async def fake(db, org_id):
        return {"total_sequences": 5, "active_sequences": 3, "total_enrolled": 100}
    monkeypatch.setattr(es_svc, "get_stats", fake)
    r = await client.get("/api/v1/email-sequences/stats")
    assert r.status_code == 200
    assert r.json()["total_sequences"] == 5


@pytest.mark.asyncio
async def test_add_sequence_step(client, monkeypatch):
    async def fake_get(db, sid, oid):
        return _obj(id=1, organization_id=1, name="S", description=None,
                     trigger_event="x", exit_condition=None, is_active=True,
                     total_enrolled=0, total_completed=0, created_by_user_id=None, created_at=TS)
    monkeypatch.setattr(es_svc, "get_sequence", fake_get)

    async def fake_add(db, *, sequence_id, step_order=1, delay_hours=24, subject, body, template_id=None):
        return _obj(id=1, sequence_id=sequence_id, step_order=step_order,
                     delay_hours=delay_hours, subject=subject, body=body,
                     template_id=template_id, created_at=TS)
    monkeypatch.setattr(es_svc, "add_step", fake_add)
    r = await client.post("/api/v1/email-sequences/1/steps", json={"subject": "Hi", "body": "Welcome"})
    assert r.status_code == 201


# ── Deal Risk Scoring ────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_deal(client, monkeypatch):
    async def fake(db, *, organization_id, deal_id, risk_score, factors=None):
        return _obj(id=1, organization_id=1, deal_id=deal_id,
                     risk_score=risk_score, risk_level="high",
                     factors_json="[]", scored_at=TS)
    monkeypatch.setattr(dr_svc, "score_deal", fake)
    r = await client.post("/api/v1/deal-risks", json={"deal_id": 1, "risk_score": 60})
    assert r.status_code == 201
    assert r.json()["risk_level"] == "high"


@pytest.mark.asyncio
async def test_list_deal_risks(client, monkeypatch):
    async def fake(db, org_id, *, risk_level=None, limit=50): return []
    monkeypatch.setattr(dr_svc, "list_risks", fake)
    r = await client.get("/api/v1/deal-risks")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_deal_risk_summary(client, monkeypatch):
    async def fake(db, org_id):
        return {"low": 5, "medium": 3, "high": 2, "critical": 1}
    monkeypatch.setattr(dr_svc, "get_risk_summary", fake)
    r = await client.get("/api/v1/deal-risks/summary")
    assert r.status_code == 200
    assert r.json()["critical"] == 1


# ── Contact Relationships ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_contact_relationship(client, monkeypatch):
    async def fake(db, *, organization_id, contact_a_id, contact_b_id, relationship_type, strength=50, notes=None):
        return _obj(id=1, organization_id=1, contact_a_id=contact_a_id,
                     contact_b_id=contact_b_id, relationship_type=relationship_type,
                     strength=strength, notes=notes, created_at=TS)
    monkeypatch.setattr(cr_svc, "create_relationship", fake)
    r = await client.post("/api/v1/contact-relationships", json={
        "contact_a_id": 1, "contact_b_id": 2, "relationship_type": "colleague",
    })
    assert r.status_code == 201
    assert r.json()["relationship_type"] == "colleague"


@pytest.mark.asyncio
async def test_list_contact_relationships(client, monkeypatch):
    async def fake(db, org_id, *, contact_id=None): return []
    monkeypatch.setattr(cr_svc, "list_relationships", fake)
    r = await client.get("/api/v1/contact-relationships")
    assert r.status_code == 200


# ── Pipeline Snapshots ───────────────────────────────────────


@pytest.mark.asyncio
async def test_create_pipeline_snapshot(client, monkeypatch):
    async def fake(db, *, organization_id, snapshot_type="daily", total_deals=0, total_value=0, stage_breakdown=None, weighted_value=0, new_deals=0, won_deals=0, lost_deals=0):
        return _obj(id=1, organization_id=1, snapshot_type=snapshot_type,
                     total_deals=total_deals, total_value=total_value,
                     stage_breakdown_json="{}", weighted_value=weighted_value,
                     new_deals=new_deals, won_deals=won_deals, lost_deals=lost_deals,
                     created_at=TS)
    monkeypatch.setattr(ps_svc, "create_snapshot", fake)
    r = await client.post("/api/v1/pipeline-snapshots", json={"total_deals": 10, "total_value": 50000})
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_list_pipeline_snapshots(client, monkeypatch):
    async def fake(db, org_id, *, snapshot_type=None, limit=30): return []
    monkeypatch.setattr(ps_svc, "list_snapshots", fake)
    r = await client.get("/api/v1/pipeline-snapshots")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_pipeline_trend(client, monkeypatch):
    async def fake(db, org_id, *, limit=14):
        return [{"date": "2026-03-10", "total_deals": 10, "total_value": 50000, "weighted_value": 30000, "won_deals": 2, "lost_deals": 1}]
    monkeypatch.setattr(ps_svc, "get_trend", fake)
    r = await client.get("/api/v1/pipeline-snapshots/trend")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ── User Activity Heatmap ────────────────────────────────────


@pytest.mark.asyncio
async def test_record_activity(client, monkeypatch):
    async def fake(db, *, organization_id, user_id, activity_type, hour_of_day, day_of_week, feature_name=None):
        return _obj(id=1, organization_id=1, user_id=user_id,
                     activity_type=activity_type, feature_name=feature_name,
                     hour_of_day=hour_of_day, day_of_week=day_of_week, created_at=TS)
    monkeypatch.setattr(ua_svc, "record_activity", fake)
    r = await client.post("/api/v1/user-activity", json={"activity_type": "login", "hour_of_day": 9, "day_of_week": 1})
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_get_heatmap(client, monkeypatch):
    async def fake(db, org_id, *, user_id=None):
        return {str(d): {str(h): 0 for h in range(24)} for d in range(7)}
    monkeypatch.setattr(ua_svc, "get_heatmap", fake)
    r = await client.get("/api/v1/user-activity/heatmap")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_top_features(client, monkeypatch):
    async def fake(db, org_id, *, limit=10):
        return [{"feature": "dashboard", "count": 42}]
    monkeypatch.setattr(ua_svc, "get_top_features", fake)
    r = await client.get("/api/v1/user-activity/top-features")
    assert r.status_code == 200
    assert r.json()[0]["feature"] == "dashboard"


# ── Document Templates ───────────────────────────────────────


@pytest.mark.asyncio
async def test_create_document_template(client, monkeypatch):
    async def fake(db, *, organization_id, name, doc_type, content, merge_fields=None, created_by_user_id=None):
        return _obj(id=1, organization_id=1, name=name, doc_type=doc_type,
                     content=content, merge_fields_json="[]", version=1,
                     is_active=True, created_by_user_id=created_by_user_id,
                     created_at=TS, updated_at=TS)
    monkeypatch.setattr(dt_svc, "create_template", fake)
    r = await client.post("/api/v1/document-templates", json={
        "name": "Proposal", "doc_type": "proposal", "content": "Dear {{name}}",
    })
    assert r.status_code == 201
    assert r.json()["name"] == "Proposal"


@pytest.mark.asyncio
async def test_list_document_templates(client, monkeypatch):
    async def fake(db, org_id, *, doc_type=None, is_active=None): return []
    monkeypatch.setattr(dt_svc, "list_templates", fake)
    r = await client.get("/api/v1/document-templates")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_render_document_template(client, monkeypatch):
    async def fake(db, template_id, org_id, data):
        return {"rendered": "Dear Nidin", "unresolved_fields": []}
    monkeypatch.setattr(dt_svc, "render_template", fake)
    r = await client.post("/api/v1/document-templates/1/render", json={"data": {"name": "Nidin"}})
    assert r.status_code == 200
    assert r.json()["rendered"] == "Dear Nidin"


# ── Goal Cascade ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_goal_cascade_link(client, monkeypatch):
    async def fake(db, *, organization_id, parent_type, parent_id, child_type, child_id, weight=1.0, notes=None):
        return _obj(id=1, organization_id=1, parent_type=parent_type,
                     parent_id=parent_id, child_type=child_type, child_id=child_id,
                     weight=weight, notes=notes, created_at=TS)
    monkeypatch.setattr(gc_svc, "create_link", fake)
    r = await client.post("/api/v1/goal-cascades", json={
        "parent_type": "goal", "parent_id": 1, "child_type": "key_result", "child_id": 2,
    })
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_list_goal_cascade_links(client, monkeypatch):
    async def fake(db, org_id, *, parent_type=None, parent_id=None): return []
    monkeypatch.setattr(gc_svc, "list_links", fake)
    r = await client.get("/api/v1/goal-cascades")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_goal_cascade_tree(client, monkeypatch):
    async def fake(db, org_id, root_type, root_id):
        return {"type": root_type, "id": root_id, "children": []}
    monkeypatch.setattr(gc_svc, "get_tree", fake)
    r = await client.get("/api/v1/goal-cascades/tree", params={"root_type": "goal", "root_id": 1})
    assert r.status_code == 200
    assert r.json()["type"] == "goal"


@pytest.mark.asyncio
async def test_goal_cascade_children(client, monkeypatch):
    async def fake(db, org_id, parent_type, parent_id): return []
    monkeypatch.setattr(gc_svc, "get_children", fake)
    r = await client.get("/api/v1/goal-cascades/children", params={"parent_type": "goal", "parent_id": 1})
    assert r.status_code == 200
