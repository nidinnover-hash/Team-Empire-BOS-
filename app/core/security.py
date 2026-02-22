import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import cast

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def create_access_token(data: dict, expires_minutes: int = 30) -> str:
    header = {"alg": settings.ALGORITHM, "typ": "JWT"}
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload["exp"] = int(expire.timestamp())

    signing_input = (
        f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))}."
        f"{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))}"
    )
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    header_b64, payload_b64, sig_b64 = token.split(".")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    provided_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError("Invalid signature")
    payload = cast(dict, json.loads(_b64url_decode(payload_b64).decode("utf-8")))
    exp = payload.get("exp")
    if exp is None or int(exp) < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("Token expired")
    return payload


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 100_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iter_str, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(digest_b64.encode())
    except Exception:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise credentials_exception from exc

    user_id = payload.get("id")
    email = payload.get("email")
    role = payload.get("role", "STAFF")
    org_id = payload.get("org_id")
    if user_id is None or email is None or org_id is None:
        raise credentials_exception

    return {"id": user_id, "email": email, "role": role, "org_id": org_id}
