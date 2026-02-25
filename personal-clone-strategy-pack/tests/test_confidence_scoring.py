from app.services.confidence import assess_agent_confidence


def test_confidence_is_high_with_memory_and_good_response() -> None:
    result = assess_agent_confidence(
        user_message="Prepare a weekly plan for my team.",
        ai_response="Here is a detailed weekly plan with owners, timelines, and checkpoints.",
        requires_approval=False,
        memory_context="Team members and priorities loaded.",
        proposed_actions_count=1,
    )
    assert result.score >= 60
    assert result.level in {"medium", "high"}
    assert result.needs_human_review is False


def test_confidence_is_low_on_provider_error() -> None:
    result = assess_agent_confidence(
        user_message="Send payroll update now",
        ai_response="Error: OpenAI quota exceeded.",
        requires_approval=True,
        memory_context="",
        proposed_actions_count=0,
    )
    assert result.score < 60
    assert result.level == "low"
    assert result.needs_human_review is True
