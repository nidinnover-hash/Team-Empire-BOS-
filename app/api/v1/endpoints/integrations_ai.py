from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    AIProviderConnectRequest,
    AIProviderConnectResult,
    AIProviderName,
    AIProviderStatus,
    AITestResult,
    CodingProjectDiscoveryRead,
)
from app.services import integration as integration_service

router = APIRouter(tags=["Integrations"])

_AI_CONNECT_TYPE_MAP: dict[str, str] = {
    "openai": "ai_openai",
    "anthropic": "ai_anthropic",
    "groq": "ai_groq",
    "gemini": "ai_gemini",
}


@router.get("/ai/status", response_model=list[AIProviderStatus])
async def ai_provider_status(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[AIProviderStatus]:
    """Check which AI providers are configured and active."""
    from app.services.ai_router import _get_key, _key_ok

    org_id = int(actor["org_id"])
    active = settings.DEFAULT_AI_PROVIDER
    email = settings.EMAIL_AI_PROVIDER or active
    providers = [
        ("openai", settings.AGENT_MODEL_OPENAI),
        ("anthropic", settings.AGENT_MODEL_ANTHROPIC),
        ("groq", settings.AGENT_MODEL_GROQ),
        ("gemini", settings.AGENT_MODEL_GEMINI),
    ]
    return [
        AIProviderStatus(
            provider=name,
            configured=_key_ok(_get_key(name, org_id=org_id)),
            active=(active == name),
            email_active=(email == name),
            model=model,
        )
        for name, model in providers
    ]


@router.post("/ai/{provider}/connect", response_model=AIProviderConnectResult, status_code=201)
async def ai_provider_connect(
    provider: AIProviderName,
    data: AIProviderConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> AIProviderConnectResult:
    """Save an AI provider API key after a live validation call."""
    from app.services.ai_router import call_ai, set_ai_key_cache

    org_id = int(actor["org_id"])
    set_ai_key_cache(provider, data.api_key, org_id=org_id)

    response = await call_ai(
        system_prompt="You are a connection test. Respond with exactly: 'Connected.'",
        user_message="ping",
        provider=provider,
        max_tokens=20,
        organization_id=org_id,
    )
    if response.startswith("Error:"):
        from app.services.ai_router import clear_ai_key_cache

        clear_ai_key_cache(provider, org_id=org_id)
        await record_action(
            db,
            event_type="ai_provider_connect_failed",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={"provider": provider, "error": response[:200]},
        )
        raise HTTPException(status_code=400, detail=response)

    integration_type = _AI_CONNECT_TYPE_MAP[provider]
    item = await integration_service.connect_integration(
        db,
        organization_id=actor["org_id"],
        integration_type=integration_type,
        config_json={"api_key": data.api_key, "connected_at": datetime.now(UTC).isoformat()},
    )
    await record_action(
        db,
        event_type="ai_provider_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=item.id,
        payload_json={"provider": provider},
    )
    return AIProviderConnectResult(
        provider=provider,
        status="connected",
        message=f"{provider.capitalize()} API key validated and saved.",
    )


@router.post("/ai/{provider}/disconnect")
async def ai_provider_disconnect(
    provider: AIProviderName,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict[str, str]:
    """Clear a cached AI provider key and disconnect the integration record."""
    from app.services.ai_router import clear_ai_key_cache

    clear_ai_key_cache(provider, org_id=int(actor["org_id"]))

    integration_type = _AI_CONNECT_TYPE_MAP[provider]
    existing = await integration_service.get_integration_by_type(db, actor["org_id"], integration_type)
    if existing:
        await integration_service.disconnect_integration(
            db,
            integration_id=existing.id,
            organization_id=actor["org_id"],
        )
    await record_action(
        db,
        event_type="ai_provider_disconnected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=existing.id if existing else None,
        payload_json={"provider": provider},
    )
    return {"status": "disconnected", "provider": provider}


@router.post("/ai/test", response_model=AITestResult)
async def test_ai_provider(
    provider: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> AITestResult:
    """Make a live provider test call."""
    from app.services.ai_router import _get_key, _key_ok, call_ai

    chosen = (provider or settings.DEFAULT_AI_PROVIDER or "").strip().lower()
    if chosen == "claude":
        chosen = "anthropic"
    if chosen not in {"openai", "anthropic", "groq", "gemini"}:
        return AITestResult(
            provider=chosen or "unknown",
            status="failed",
            message="Unsupported provider. Use one of: openai, claude, anthropic, groq, gemini.",
        )

    org_id = int(actor["org_id"])
    if not _key_ok(_get_key(chosen, org_id=org_id)):
        return AITestResult(
            provider=chosen,
            status="not_configured",
            message=f"{chosen.upper()} API key is missing. Add it via .env or POST /ai/{chosen}/connect.",
        )

    response = await call_ai(
        system_prompt="You are a connection test. Respond with exactly: 'Connected.'",
        user_message="ping",
        provider=chosen,
        max_tokens=20,
        organization_id=actor["org_id"],
    )
    if response.startswith("Error:"):
        await record_action(
            db,
            event_type="ai_test_failed",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={"provider": chosen, "error": response},
        )
        return AITestResult(provider=chosen, status="failed", message=response)

    await record_action(
        db,
        event_type="ai_test_passed",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json={"provider": chosen},
    )
    return AITestResult(
        provider=chosen,
        status="ok",
        message=f"{chosen.capitalize()} is connected and responding.",
        sample_response=response,
    )


@router.get("/ai/coding-discovery", response_model=CodingProjectDiscoveryRead)
async def ai_coding_discovery(
    project_name: str | None = Query(None, max_length=120),
    language: str | None = Query(None, max_length=60),
    stage: str | None = Query(None, max_length=60),
    _actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> CodingProjectDiscoveryRead:
    """Return coding-project discovery questions before implementation."""
    p = (project_name or "project").strip()
    lang = (language or "stack").strip()
    s = (stage or "planning").strip()
    questions = [
        f"What is the exact outcome you want for {p} in this phase?",
        "What are the top 3 blockers today?",
        f"What tech stack and runtime versions are required ({lang})?",
        "What constraints exist (deadline, budget, infra, compliance)?",
        "What is the current architecture and where does this change fit?",
        "What are the acceptance criteria and measurable success metrics?",
        "What risks are unacceptable (downtime, data loss, security regressions)?",
        "What tests must pass before release?",
        "Who approves production changes and what is rollback plan?",
        "Which tasks can be automated safely vs require manual approval?",
    ]
    next_prompt = (
        f"You are my senior coding assistant for {p}. Current stage: {s}. "
        "Ask concise discovery questions first, then propose an implementation plan "
        "with risks, tests, and rollout steps."
    )
    return CodingProjectDiscoveryRead(
        provider_options=["openai", "claude", "groq", "gemini"],
        questions=questions,
        next_prompt=next_prompt,
    )
