"""
AI Router — single entry point for all LLM calls.

All agent, memory, and email AI calls go through call_ai().
Never call OpenAI or Anthropic directly from other files.
"""

from app.core.config import settings

_PLACEHOLDER_KEYS = {"sk-your-key-here", "sk-xxxxxxxxxxxxxxxxxxxxxxxx", "", "your-anthropic-key-here"}


async def call_ai(
    system_prompt: str,
    user_message: str,
    memory_context: str = "",
    provider: str | None = None,
    max_tokens: int = 800,
) -> str:
    """
    Route to OpenAI or Anthropic based on config.

    Args:
        system_prompt:  Role-specific instructions for the AI.
        user_message:   What the user typed.
        memory_context: Injected team/profile memory (optional).
        provider:       "openai" or "anthropic". None = use DEFAULT_AI_PROVIDER.
        max_tokens:     Max response length.

    Returns:
        AI response as a string.
        Returns a safe fallback message on any error — never raises.
    """
    chosen = provider or settings.DEFAULT_AI_PROVIDER

    # Inject memory into system prompt if provided
    full_system = system_prompt
    if memory_context:
        full_system = f"[MEMORY CONTEXT]\n{memory_context}\n[END MEMORY]\n\n{system_prompt}"

    if chosen == "anthropic":
        return await _call_anthropic(full_system, user_message, max_tokens)

    return await _call_openai(full_system, user_message, max_tokens)


async def _call_openai(system_prompt: str, user_message: str, max_tokens: int) -> str:
    key = settings.OPENAI_API_KEY
    if not key or key in _PLACEHOLDER_KEYS:
        return "OpenAI not configured. Add OPENAI_API_KEY to your .env file."
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=key)
        result = await client.chat.completions.create(
            model=settings.AGENT_MODEL_OPENAI,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
            timeout=20.0,
        )
        return result.choices[0].message.content or "No response from OpenAI."
    except Exception as e:
        return f"OpenAI error: {type(e).__name__}. Check your API key and network."


async def _call_anthropic(system_prompt: str, user_message: str, max_tokens: int) -> str:
    key = settings.ANTHROPIC_API_KEY
    if not key or key in _PLACEHOLDER_KEYS:
        return "Anthropic not configured. Add ANTHROPIC_API_KEY to your .env file."
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=key)
        result = await client.messages.create(
            model=settings.AGENT_MODEL_ANTHROPIC,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return result.content[0].text or "No response from Anthropic."
    except Exception as e:
        return f"Anthropic error: {type(e).__name__}. Check your API key and network."
