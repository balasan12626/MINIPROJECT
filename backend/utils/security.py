from datetime import datetime, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

VALID_ROLES = {"ADMIN", "OPERATOR", "ANALYST", "VIEWER"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def authenticate_user(username: str, password: str) -> dict | None:
    """Return {username, role} if credentials match configured users."""
    settings = get_settings()
    users = {
        settings.admin_username: ("ADMIN", settings.admin_password),
        settings.operator_username: ("OPERATOR", settings.operator_password),
        settings.analyst_username: ("ANALYST", settings.analyst_password),
        settings.viewer_username: ("VIEWER", settings.viewer_password),
    }
    entry = users.get(username)
    if not entry:
        return None
    role, expected = entry
    if password != expected:
        return None
    return {"username": username, "role": role}


def verify_password(plain: str, username: str) -> bool:
    return authenticate_user(username, plain) is not None


def create_token(username: str, role: str = "OPERATOR") -> str:
    settings = get_settings()
    role_u = (role or "OPERATOR").upper()
    if role_u not in VALID_ROLES:
        role_u = "OPERATOR"
    payload = {
        "sub": username,
        "role": role_u,
        "iat": int(utcnow().timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("role"):
            payload["role"] = str(payload["role"]).upper()
        return payload
    except JWTError:
        return None


def role_allowed(payload: dict | None, action: str) -> bool:
    if payload is None:
        return False
    role = str(payload.get("role") or "").upper()
    if action in {"review", "override", "assign", "sos_ack", "mutate", "reset"}:
        return role in {"OPERATOR", "ADMIN"}
    if action in {"benchmark", "predict"}:
        return role in {"ANALYST", "OPERATOR", "ADMIN"}
    return role in VALID_ROLES
