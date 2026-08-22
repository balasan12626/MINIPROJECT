from datetime import datetime, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def verify_password(plain: str, username: str) -> bool:
    settings = get_settings()
    return plain == settings.operator_password and username == settings.operator_username


def create_token(username: str) -> str:
    settings = get_settings()
    payload = {"sub": username, "role": "operator", "iat": int(utcnow().timestamp())}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def role_allowed(payload: dict | None, action: str) -> bool:
    if payload is None:
        return False
    role = payload.get("role")
    if action in {"review", "override", "assign", "sos_ack"}:
        return role in {"operator", "admin"}
    return bool(role)
