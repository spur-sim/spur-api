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

import hashlib
import hmac
from typing import Protocol

from fastapi import Header, HTTPException, status

from spur_api.config import settings


def key_fingerprint(key: str) -> str:
    return "key:" + hashlib.sha256(key.encode()).hexdigest()[:12]


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
    if not any(hmac.compare_digest(token, k) for k in settings.api_keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    # The principal id ends up stored as a project's `owner` and returned
    # in API responses, so it must never be the secret key itself.
    return StaticPrincipal(id=key_fingerprint(token))
