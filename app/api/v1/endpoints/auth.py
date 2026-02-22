import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.security import create_access_token, get_current_user, verify_password
from app.logs.audit import record_action
from app.services import user as user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.get_user_by_email(db, username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Failed login attempt for '%s' from %s", username, client_ip)
        await record_action(
            db,
            event_type="login_failed",
            actor_user_id=None,
            organization_id=user.organization_id if user else 1,
            entity_type="user",
            entity_id=user.id if user else None,
            payload_json={"username": username[:200], "ip": client_ip},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/password",
        )
    access_token = create_access_token(
        {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "org_id": user.organization_id,
        },
        expires_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user
