from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any


def get_workflow_handlers() -> dict[str, Callable[..., Any]]:
    from app.services.execution_engine import HANDLERS

    return HANDLERS


async def dispatch_workflow_step_handler(action_type: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    handler = get_workflow_handlers().get(action_type)
    if handler is None:
        return ("skipped", {"reason": f"no handler for {action_type}"})
    if asyncio.iscoroutinefunction(handler) or inspect.isasyncgenfunction(handler):
        result = await asyncio.wait_for(handler(params), timeout=30)
    else:
        result = handler(params)
        if asyncio.iscoroutine(result):
            result = await asyncio.wait_for(result, timeout=30)
    if not isinstance(result, dict):
        result = {"output": str(result)}
    return ("succeeded", result)
