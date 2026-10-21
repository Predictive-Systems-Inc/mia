"""FastAPI dependencies: the database session and the authenticated actor (ADR 011).

`current_auth` resolves, in order, a bearer token, the `mia_at` cookie and, in dev mode only,
the X-Mia-Actor header from a loopback peer without Cloudflare headers. No credential is 401,
an inactive person 403. Roles come from the person row on every request, never from a token.
"""

import ipaddress
import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from mia.core import auth, events
from mia.core.db import session_scope, utcnow
from mia.core.models import Actor, AuthClient, AuthDevice, Person
from mia.settings import Settings, get_settings

log = logging.getLogger(__name__)
ACCESS_COOKIE, REFRESH_COOKIE = "mia_at", "mia_rt"
_dev_header_seen: set[str] = set()


def get_session() -> Iterator[Session]:
    """One session per request: commits on success, rolls back on error, always closes."""
    with session_scope() as session:
        yield session


# "function": commit before the response is sent, so a failed commit is a 500, not a lost write.
DbSession = Annotated[Session, Depends(get_session, scope="function")]


class AuthContext(BaseModel):
    """Who is acting on this request and how they were verified."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    actor: Actor
    person: Person | None = None
    client: AuthClient | None = None
    method: str  # password_totp, password, phone_otp, device, wa_link, client, enrol, dev
    aal: str  # aal1, aal2, client, enrol, dev
    session_id: str | None = None
    channel: str = "app"
    via: Literal["bearer", "cookie", "header"]
    stepped_up_at: datetime | None = None


def public_origin() -> str:
    """scheme://host[:port] of MIA_PUBLIC_URL (the cookie and CSRF origin)."""
    parts = urlsplit(get_settings().MIA_PUBLIC_URL)
    return f"{parts.scheme}://{parts.netloc}"


def _trusted_proxy(peer: str) -> bool:
    """MIA_TRUSTED_PROXIES holds addresses or networks (the compose network for cloudflared)."""
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for entry in get_settings().MIA_TRUSTED_PROXIES.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if address in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request) -> str:
    """The TCP peer, or CF-Connecting-IP when the peer is a trusted proxy."""
    peer = request.client.host if request.client else ""
    if _trusted_proxy(peer):
        return request.headers.get("cf-connecting-ip", peer)
    return peer


def _loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def direct_loopback(request: Request) -> bool:
    """True only for a loopback peer with no Cloudflare header (not tunnelled from outside)."""
    return (
        _loopback(request)
        and "cf-connecting-ip" not in request.headers
        and "cf-ray" not in request.headers
    )


def check_mode(settings: Settings) -> None:
    """Refuse dev mode on anything but localhost (called at startup)."""
    host = urlsplit(settings.MIA_PUBLIC_URL).hostname or ""
    if settings.MIA_AUTH_MODE == "dev" and host not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError(
            "MIA_AUTH_MODE=dev accepts the X-Mia-Actor header; "
            f"refusing to serve {settings.MIA_PUBLIC_URL}"
        )


def _credential(request: Request) -> tuple[str, Literal["bearer", "cookie"]] | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip(), "bearer"
    cookie = request.cookies.get(ACCESS_COOKIE)
    return (cookie, "cookie") if cookie else None


def _dev_header(request: Request, session: Session) -> AuthContext | None:
    settings = get_settings()
    actor_id = request.headers.get("x-mia-actor")
    if settings.MIA_AUTH_MODE != "dev" or not actor_id or request.url.path.startswith("/auth/"):
        return None
    if not direct_loopback(request):
        return None
    person = session.get(Person, actor_id)
    if person is None or person.status != "active":
        raise HTTPException(403, "unknown actor")
    if person.id not in _dev_header_seen:
        _dev_header_seen.add(person.id)
        events.emit(session, "auth.dev_header_used", person, None, None, Actor.person(person))
    return AuthContext(
        actor=Actor.person(person), person=person, method="dev", aal="dev", via="header"
    )


def _fresh(stepped_up_at: datetime | None) -> bool:
    return stepped_up_at is not None and utcnow() - stepped_up_at <= auth.STEP_UP_TTL


def current_auth(request: Request, session: DbSession) -> AuthContext:
    """The verified actor of the request (see the module docstring)."""
    found = _credential(request)
    if found is None:
        ctx = _dev_header(request, session)
        if ctx is None:
            raise HTTPException(401, auth.INVALID)
        return ctx
    token, via = found
    unsafe = request.method not in ("GET", "HEAD", "OPTIONS")
    if via == "cookie" and unsafe and request.headers.get("origin") != public_origin():
        raise HTTPException(403, "origin not allowed")
    row = auth.verify_access(session, token, utcnow())
    if row is None:
        raise HTTPException(401, auth.INVALID)
    if row.subject_type == "client":
        client = session.get(AuthClient, row.subject_id)
        expired = (
            client is not None and client.expires_at is not None and client.expires_at <= utcnow()
        )
        if client is None or client.status != "active" or expired:
            raise HTTPException(401, auth.INVALID)
        return AuthContext(
            actor=auth.client_actor(client),
            client=client,
            method=row.method,
            aal=row.aal,
            session_id=row.id,
            via=via,
        )
    person = session.get(Person, row.subject_id)
    if person is None or person.status != "active":
        raise HTTPException(403, "person is not active")
    aal = row.aal
    if row.device_id and _fresh(row.stepped_up_at):
        device = session.get(AuthDevice, row.device_id)
        if device is not None and device.kind == "mobile":
            aal = "aal2"  # a bound device plus the PIN (spec section 3)
    return AuthContext(
        actor=Actor.person(person),
        person=person,
        method=row.method,
        aal=aal,
        session_id=row.id,
        via=via,
        stepped_up_at=row.stepped_up_at,
    )


CurrentAuth = Annotated[AuthContext, Depends(current_auth)]


def current_person(auth_ctx: CurrentAuth) -> AuthContext:
    """A signed-in person with a full session: clients and enrolment sessions get 403."""
    if auth_ctx.person is None:
        raise HTTPException(403, "a person must be signed in")
    if auth_ctx.aal == "enrol":
        raise HTTPException(403, "finish enrolment first")
    return auth_ctx


PersonAuth = Annotated[AuthContext, Depends(current_person)]


def current_client(auth_ctx: CurrentAuth) -> AuthContext:
    """An outside client with a client token; anything else is 401 (ADR 008)."""
    if auth_ctx.client is None:
        raise HTTPException(401, auth.INVALID)
    return auth_ctx


ClientAuth = Annotated[AuthContext, Depends(current_client)]


def set_cookies(response: Response, tokens: auth.Tokens) -> None:
    """Access and refresh cookies: HttpOnly, SameSite=Strict, Secure when the node is https."""
    secure = public_origin().startswith("https://")
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access,
        max_age=int(auth.ACCESS_TTL.total_seconds()),
        path="/",
        httponly=True,
        secure=secure,
        samesite="strict",
    )
    if tokens.refresh:
        response.set_cookie(
            REFRESH_COOKIE,
            tokens.refresh,
            max_age=int(auth.OFFICE_MAX.total_seconds()),
            path="/auth/refresh",
            httponly=True,
            secure=secure,
            samesite="strict",
        )


def clear_cookies(response: Response) -> None:
    """Drop both cookies."""
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/auth/refresh")
