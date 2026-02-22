from collections.abc import AsyncGenerator

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, get_current_user
from app.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one DB session per request, always closed on exit."""
    async with AsyncSessionLocal() as session:
        yield session


def get_current_org_id(user: dict = Depends(get_current_user)) -> int:
    return int(user["org_id"])


def get_current_web_user(
    session_token: str | None = Cookie(default=None, alias="pc_session"),
) -> dict:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    try:
        payload = decode_access_token(session_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc
    user_id = payload.get("id")
    email = payload.get("email")
    role = payload.get("role", "STAFF")
    org_id = payload.get("org_id")
    if user_id is None or email is None or org_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session payload")
    return {"id": user_id, "email": email, "role": role, "org_id": org_id}


def verify_csrf(
    csrf_cookie: str | None = Cookie(default=None, alias="pc_csrf"),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
