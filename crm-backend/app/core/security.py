"""JWT auth — placeholder. Implement once auth endpoints are ready."""

# from datetime import datetime, timedelta, timezone
# from jose import JWTError, jwt
# from passlib.context import CryptContext
# from app.core.config import settings
#
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
#
#
# def hash_password(plain: str) -> str:
#     return pwd_context.hash(plain)
#
#
# def verify_password(plain: str, hashed: str) -> bool:
#     return pwd_context.verify(plain, hashed)
#
#
# def create_access_token(subject: str | int) -> str:
#     expire = datetime.now(timezone.utc) + timedelta(
#         minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
#     )
#     payload = {"sub": str(subject), "exp": expire}
#     return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGO)
#
#
# def decode_access_token(token: str) -> str:
#     payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGO])
#     return payload["sub"]
