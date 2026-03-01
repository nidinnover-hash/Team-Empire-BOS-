from app.services import organization as organization_service


async def test_update_feature_flags_handles_non_numeric_rollout(db):
    updated = await organization_service.update_feature_flags(
        db,
        organization_id=1,
        flags={
            "beta_access": {
                "enabled": True,
                "rollout_percentage": "not-a-number",
            }
        },
    )
    assert updated is not None
    _, flags = updated
    assert flags["beta_access"]["enabled"] is True
    assert flags["beta_access"]["rollout_percentage"] == 100


async def test_update_feature_flags_clamps_rollout_out_of_range(db):
    updated = await organization_service.update_feature_flags(
        db,
        organization_id=1,
        flags={
            "alpha": {"enabled": True, "rollout_percentage": 1000},
            "legacy": {"enabled": False, "rollout_percentage": -25},
        },
    )
    assert updated is not None
    _, flags = updated
    assert flags["alpha"]["rollout_percentage"] == 100
    assert flags["legacy"]["rollout_percentage"] == 0


async def test_update_feature_flags_defaults_rollout_when_missing_or_none(db):
    updated = await organization_service.update_feature_flags(
        db,
        organization_id=1,
        flags={
            "enabled_default": {"enabled": True},
            "disabled_default": {"enabled": False},
            "none_rollout": {"enabled": False, "rollout_percentage": None},
        },
    )
    assert updated is not None
    _, flags = updated
    assert flags["enabled_default"]["rollout_percentage"] == 100
    assert flags["disabled_default"]["rollout_percentage"] == 0
    assert flags["none_rollout"]["rollout_percentage"] == 0
