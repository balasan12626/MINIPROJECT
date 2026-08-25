"""Auth disabled for this private IEEE demo — mutations never require JWT."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)

ADMIN = "ADMIN"
OPERATOR = "OPERATOR"
ANALYST = "ANALYST"
VIEWER = "VIEWER"

MUTATION_ROLES = (ADMIN, OPERATOR)
ANALYST_PLUS = (ADMIN, OPERATOR, ANALYST)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> dict:
    # Always open — no 401 / login required
    return {"username": "demo", "role": OPERATOR, "payload": {}, "dev_open": True}


def require_roles(*_roles: str):
    def _dep(user: Annotated[dict, Depends(get_current_user)]) -> dict:
        return user

    return _dep


RequireOperator = Annotated[dict, Depends(require_roles(*MUTATION_ROLES))]
RequireAnalyst = Annotated[dict, Depends(require_roles(*ANALYST_PLUS))]
RequireAuth = Annotated[dict, Depends(get_current_user)]
