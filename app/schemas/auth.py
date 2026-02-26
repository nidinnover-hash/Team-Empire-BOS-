from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMeRead(BaseModel):
    id: int
    email: str
    role: str
    org_id: int


class WebLoginResponse(BaseModel):
    status: str
    email: str
    role: str


class WebLogoutResponse(BaseModel):
    status: str


class WebSessionUser(BaseModel):
    id: int
    email: str
    role: str
    org_id: int
    purpose: str
    default_theme: str
    default_avatar_mode: str


class WebSessionResponse(BaseModel):
    logged_in: bool
    user: WebSessionUser | None = None


class WebApiTokenResponse(BaseModel):
    token: str
