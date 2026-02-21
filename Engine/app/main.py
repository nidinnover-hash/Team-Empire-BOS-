import os
import time
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from openai import OpenAI
from pydantic import BaseModel

from app.storage import clear_memory, clear_session_memory, get_memory, get_session_memory, log_message

# Load .env from workspace root (d:\Personal Clone\.env)
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

APP_NAME = os.getenv("APP_NAME", "Personal AI Clone")
APP_VERSION = os.getenv("APP_VERSION", "1.2")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
CLONE_API_KEY = os.getenv("CLONE_API_KEY")
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "20"))

app = FastAPI(title=APP_NAME, version=APP_VERSION)

_rate_limit_hits: dict[str, deque[float]] = {}
_rate_limit_lock = Lock()


class Command(BaseModel):
    text: str
    session_id: str = "default"
    use_memory: bool = True


def _build_messages(user_text: str, session_id: str, include_memory: bool) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are Nidin's personal AI clone. "
                "Be direct, practical, and action-oriented."
            ),
        }
    ]

    if include_memory:
        history = get_session_memory(session_id)
        recent_turns = history[-12:] if len(history) > 12 else history
        for turn in recent_turns:
            role = turn.get("role")
            content = turn.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})
    return messages


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail=(
                "OPENAI_API_KEY is missing. Add it to d:\\Personal Clone\\.env "
                "and restart the server."
            ),
        )
    return OpenAI(api_key=api_key)


def _verify_api_key(x_api_key: str | None) -> None:
    if not CLONE_API_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "CLONE_API_KEY is missing. Add it to d:\\Personal Clone\\.env "
                "and restart the server."
            ),
        )
    if x_api_key != CLONE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _enforce_rate_limit(identifier: str) -> None:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    with _rate_limit_lock:
        hits = _rate_limit_hits.setdefault(identifier, deque())
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded: max {RATE_LIMIT_MAX_REQUESTS} requests per "
                    f"{RATE_LIMIT_WINDOW_SECONDS} seconds"
                ),
            )
        hits.append(now)


@app.get("/")
def home() -> dict[str, str]:
    return {"status": "running", "message": "Clone is alive"}


@app.post("/command")
def command(
    cmd: Command,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _verify_api_key(x_api_key)
    client_ip = request.client.host if request.client else "unknown"
    identifier = f"{x_api_key}:{client_ip}"
    _enforce_rate_limit(identifier)

    entry = log_message(session_id=cmd.session_id, role="user", content=cmd.text)
    client = _get_client()

    try:
        ai = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=_build_messages(cmd.text, cmd.session_id, cmd.use_memory),
            timeout=20,
        )
        ai_reply = ai.choices[0].message.content or ""
        assistant_entry = log_message(session_id=cmd.session_id, role="assistant", content=ai_reply)
        return {
            "logged_user": entry,
            "logged_assistant": assistant_entry,
            "ai_reply": ai_reply,
            "model": OPENAI_MODEL,
            "session_id": cmd.session_id,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory")
def memory(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    _verify_api_key(x_api_key)
    if session_id:
        return get_session_memory(session_id)
    return get_memory()


@app.delete("/memory")
def memory_delete(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session_id: str | None = Query(default=None),
) -> dict[str, Any]:
    _verify_api_key(x_api_key)
    if session_id:
        deleted = clear_session_memory(session_id)
        return {"status": "ok", "message": "Session memory cleared", "session_id": session_id, "deleted": deleted}
    clear_memory()
    return {"status": "ok", "message": "Memory cleared"}
