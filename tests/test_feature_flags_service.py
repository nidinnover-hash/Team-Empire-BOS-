from app.core.config import settings
from app.services import feature_flags
from app.services import organization as organization_service


async def test_feature_flag_disabled_when_not_set(db):
    enabled = await feature_flags.is_feature_enabled(
        db,
        organization_id=1,
        flag_name="does_not_exist",
    )
    assert enabled is False


async def test_feature_flag_enabled_without_subject_when_rollout_positive(db):
    updated = await organization_service.update_feature_flags(
        db,
        organization_id=1,
        flags={"flag_a": {"enabled": True, "rollout_percentage": 10}},
    )
    assert updated is not None
    enabled = await feature_flags.is_feature_enabled(
        db,
        organization_id=1,
        flag_name="flag_a",
    )
    assert enabled is True


async def test_feature_flag_subject_rollout_is_deterministic(db):
    updated = await organization_service.update_feature_flags(
        db,
        organization_id=1,
        flags={"flag_b": {"enabled": True, "rollout_percentage": 35}},
    )
    assert updated is not None
    first = await feature_flags.is_feature_enabled(
        db,
        organization_id=1,
        flag_name="flag_b",
        subject_key="user-42",
    )
    second = await feature_flags.is_feature_enabled(
        db,
        organization_id=1,
        flag_name="flag_b",
        subject_key="user-42",
    )
    assert first == second


async def test_feature_flag_respects_zero_rollout_for_subject(db):
    updated = await organization_service.update_feature_flags(
        db,
        organization_id=1,
        flags={"flag_c": {"enabled": True, "rollout_percentage": 0}},
    )
    assert updated is not None
    enabled = await feature_flags.is_feature_enabled(
        db,
        organization_id=1,
        flag_name="flag_c",
        subject_key="any-user",
    )
    assert enabled is False


async def test_effective_feature_flag_falls_back_to_global_setting(db, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_QUOTES", True)
    enabled = await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=1,
        flag_name="quotes",
    )
    assert enabled is True


async def test_effective_feature_flag_org_override_can_disable_global(db, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_QUOTES", True)
    updated = await organization_service.update_feature_flags(
        db,
        organization_id=1,
        flags={"quotes": {"enabled": False, "rollout_percentage": 0}},
    )
    assert updated is not None
    enabled = await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=1,
        flag_name="quotes",
    )
    assert enabled is False
