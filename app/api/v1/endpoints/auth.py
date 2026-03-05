from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_api_user, get_db
from app.core.middleware import get_client_ip
from app.schemas.auth import TokenResponse, UserMeRead
from app.web._helpers import (
    authenticate_user,
    create_jwt,
    enforce_password_login_policy,
    resolve_login_organization,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    username: str = Form(..., min_length=3, max_length=254),
    password: str = Form(..., min_length=8, max_length=128),
    totp_code: str | None = Form(None, min_length=6, max_length=6),
    organization_id: int | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    enforce_password_login_policy()
    client_ip = get_client_ip(request)
    user = await authenticate_user(
        db=db,
        username=username,
        password=password,
        client_ip=client_ip,
        endpoint="/api/v1/auth/login",
        totp_code=totp_code,
    )
    selected_org_id, selected_role = await resolve_login_organization(
        db,
        user=user,
        requested_org_id=organization_id,
    )
    mfa_bootstrap = bool(settings.ACCOUNT_MFA_REQUIRED and not getattr(user, "mfa_enabled", False))
    return {
        "access_token": create_jwt(
            user,
            mfa_bootstrap=mfa_bootstrap,
            org_id=selected_org_id,
            role=selected_role,
        ),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserMeRead)
async def me(user: dict = Depends(get_current_api_user)):
    return user
