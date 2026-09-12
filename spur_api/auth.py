"""Pluggable authentication.

spur-api is meant to stay a minimal, single-tenant, self-hostable service —
no built-in multi-tenant users/orgs/roles. `AuthBackend` is the seam a
future hosted layer (or a self-hoster with different requirements) can
replace without touching route code: every router depends on
`current_principal`, never on a concrete backend.

Phase 1 ships the simplest possible backend: if `auth_enabled` is False
(the default), every request is treated as an anonymous principal. When
`auth_enabled` is True, a request must carry `Authorization: Bearer <key>`
matching one of `settings.api_keys`.
"""

from typing import Protocol

from fastapi import Header, HTTPException, status

from spur_api.config import settings


class Principal(Protocol):
    id: str


class StaticPrincipal:
    def __init__(self, id: str) -> None:
        self.id = id


ANONYMOUS = StaticPrincipal(id="anonymous")


def current_principal(
    authorization: str | None = Header(default=None),
) -> StaticPrincipal:
    if not settings.auth_enabled:
        return ANONYMOUS

    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if token not in settings.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    return StaticPrincipal(id=token)
