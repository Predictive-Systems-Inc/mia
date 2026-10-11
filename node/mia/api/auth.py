"""Authentication routes (ADR 011): office login with password and TOTP, enrolment, refresh,
logout, and (later tasks) staff codes, devices, PIN step-up, clients and administration.

Web clients (header `X-Mia-Client: web`) get HttpOnly cookies and no tokens in the body;
everything else gets bearer tokens. Every failure is 401 `invalid credentials`.
"""

import base64
import html
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from mia.api.deps import (
    REFRESH_COOKIE,
    AuthContext,
    CurrentAuth,
    DbSession,
    PersonAuth,
    clear_cookies,
    client_ip,
    public_origin,
    set_cookies,
)
from mia.core import auth, keys
from mia.core.db import utcnow
from mia.core.models import Actor, AuthCode, AuthDevice, AuthSession, Person

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class MfaIn(BaseModel):
    mfa_token: str = Field(max_length=100)
    code: str = Field(max_length=20)


class CodeIn(BaseModel):
    code: str = Field(max_length=20)


class PasswordIn(BaseModel):
    password: str = Field(max_length=200)
    email: str | None = Field(default=None, max_length=200)
    current: str | None = Field(default=None, max_length=200)  # required once a password exists


class RefreshIn(BaseModel):
    refresh: str | None = Field(default=None, max_length=100)


class TokensOut(BaseModel):
    access: str | None = None
    refresh: str | None = None
    aal: str
    enrol: bool = False


def _web(request: Request) -> bool:
    return request.headers.get("x-mia-client", "").lower() == "web"


def _tokens_response(request: Request, response: Response, tokens: auth.Tokens) -> TokensOut:
    """Cookies for the web, tokens in the body for everyone else."""
    enrol = tokens.row.aal == "enrol"
    if _web(request):
        set_cookies(response, tokens)
        return TokensOut(aal=tokens.row.aal, enrol=enrol)
    return TokensOut(access=tokens.access, refresh=tokens.refresh, aal=tokens.row.aal, enrol=enrol)


def _person(ctx: AuthContext) -> Person:
    if ctx.person is None:
        raise HTTPException(403, "a person must be signed in")
    return ctx.person


def _invalid() -> HTTPException:
    return HTTPException(401, auth.INVALID)


def _office_credentials_allowed(ctx: AuthContext) -> None:
    """Setting a password or enrolling TOTP needs an office-grade session (aal2, an enrolment
    link, or a password login that is enrolling its first factor). A phone or device session
    must not turn into an office login."""
    if ctx.aal not in ("aal2", "enrol") and ctx.method != "password":
        raise HTTPException(403, "sign in with your password or an enrolment link first")


@router.post("/login")
def login(
    request: Request, response: Response, session: DbSession, body: LoginIn
) -> dict[str, object]:
    """Password first. People with MFA get an mfa_token for POST /auth/mfa; a person who must
    have MFA but has none gets an enrolment session; everyone else is signed in (aal1)."""
    now, ip = utcnow(), client_ip(request)
    try:
        person = auth.check_password(session, body.email, body.password, ip, now)
    except auth.AuthError:
        raise _invalid() from None
    actor = Actor.person(person)
    if auth.has_mfa(session, person):
        token = auth.create_code(session, actor, person, "mfa", now, address=ip, token=True)
        return {"mfa_required": True, "mfa_token": token}
    if auth.needs_mfa(session, person):
        tokens = auth.issue_session(session, person, method="enrol", aal="enrol", ip=ip, now=now)
    else:
        tokens = auth.issue_session(session, person, method="password", aal="aal1", ip=ip, now=now)
    return _tokens_response(request, response, tokens).model_dump()


@router.post("/mfa", response_model=TokensOut)
def mfa(request: Request, response: Response, session: DbSession, body: MfaIn) -> TokensOut:
    """Second step: a TOTP code or a recovery code against the mfa_token."""
    now, ip = utcnow(), client_ip(request)
    found = auth.check_code(session, "mfa", body.mfa_token, now)
    if found.status != "ok" or found.row is None:
        raise _invalid()
    person = session.get(Person, found.row.person_id)
    if person is None or person.status != "active":
        raise _invalid()
    actor = Actor.person(person)
    key = auth.attempt_key(person.id, ip)  # per person, so fresh tokens do not reset the count
    if auth.throttled(session, "mfa", key, now):
        raise _invalid()
    ok = auth.check_totp(session, person, body.code, now) or auth.check_recovery(
        session, actor, person, body.code, now
    )
    auth.record_attempt(session, "mfa", key, ok, now, actor=actor)
    if not ok:
        auth.fail_code(session, "mfa", now, person_id=person.id)
        raise _invalid()
    auth.use_code(session, actor, found.row, now)
    auth.unlock_pin(session, actor, person, now)
    tokens = auth.issue_session(session, person, method="password_totp", aal="aal2", ip=ip, now=now)
    return _tokens_response(request, response, tokens)


@router.post("/mfa/enrol")
def mfa_enrol(session: DbSession, ctx: CurrentAuth) -> dict[str, str]:
    """Start TOTP enrolment (from an office session or an enrolment session)."""
    person = _person(ctx)
    _office_credentials_allowed(ctx)
    _, uri = auth.enrol_totp(session, ctx.actor, person, utcnow())
    return {"uri": uri}


@router.post("/mfa/confirm")
def mfa_confirm(
    request: Request, response: Response, session: DbSession, ctx: CurrentAuth, body: CodeIn
) -> dict[str, object]:
    """Confirm TOTP with a first code: recovery codes come back once, and an enrolment session
    becomes a full aal2 session."""
    person = _person(ctx)
    now = utcnow()
    cred = auth.credential(session, person.id, "totp", ("pending",))
    if cred is None:
        raise HTTPException(400, "start enrolment first")
    try:
        codes = auth.confirm_totp(session, ctx.actor, cred, body.code, now)
    except auth.AuthError:
        raise _invalid() from None
    out: dict[str, object] = {"recovery_codes": codes}
    if ctx.aal == "enrol":
        auth.revoke_sessions(session, ctx.actor, person.id, now)
        tokens = auth.issue_session(
            session, person, method="password_totp", aal="aal2", ip=client_ip(request), now=now
        )
        out.update(_tokens_response(request, response, tokens).model_dump())
    return out


@router.post("/password")
def set_password(
    request: Request, session: DbSession, ctx: CurrentAuth, body: PasswordIn
) -> dict[str, bool]:
    """Set the password (and email on first set). Changing an existing password needs the
    current one, except from an enrolment link. Every other session of the person ends."""
    person = _person(ctx)
    _office_credentials_allowed(ctx)
    now = utcnow()
    current = auth.credential(session, person.id, "password")
    email = body.email or (current.login if current else None)
    if not email:
        raise HTTPException(400, "email required")
    if current is not None and current.secret_hash and ctx.aal != "enrol":
        key = auth.attempt_key(person.id, client_ip(request))
        if auth.throttled(session, "password_change", key, now):
            raise _invalid()
        ok = body.current is not None and keys.verify_secret(body.current, current.secret_hash)
        auth.record_attempt(session, "password_change", key, ok, now, actor=ctx.actor)
        if not ok:
            raise _invalid()
    try:
        auth.set_password(session, ctx.actor, person, email, body.password, now)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    auth.revoke_sessions(session, ctx.actor, person.id, now, keep=ctx.session_id)
    return {"ok": True}


@router.post("/refresh", response_model=TokensOut)
def refresh(
    request: Request, response: Response, session: DbSession, body: RefreshIn | None = None
) -> TokensOut:
    """Rotate tokens with the refresh token (body, or the mia_rt cookie for the web)."""
    from_body = body.refresh if body else None
    token = from_body or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise _invalid()
    if not from_body and request.headers.get("origin") != public_origin():
        raise HTTPException(403, "origin not allowed")  # cookie refresh needs the site's Origin
    try:
        tokens = auth.refresh_session(session, token, utcnow())
    except auth.AuthError:
        clear_cookies(response)
        raise _invalid() from None
    return _tokens_response(request, response, tokens)


@router.post("/logout")
def logout(response: Response, session: DbSession, ctx: CurrentAuth) -> dict[str, bool]:
    """End this session; a mobile device signing out is revoked with it."""
    now = utcnow()
    row = session.get(AuthSession, ctx.session_id) if ctx.session_id else None
    if row is not None:
        device = session.get(AuthDevice, row.device_id) if row.device_id else None
        if device is not None and device.kind == "mobile":
            auth.revoke_device(session, ctx.actor, device, now)
        else:
            auth.revoke_session(session, ctx.actor, row, now)
    clear_cookies(response)
    return {"ok": True}


@router.get("/me")
def me(session: DbSession, ctx: CurrentAuth) -> dict[str, object]:
    """Who is signed in and how."""
    if ctx.person is None:
        client_id = ctx.client.client_id if ctx.client else None
        return {"client_id": client_id, "aal": ctx.aal, "method": ctx.method}
    person = ctx.person
    fresh = ctx.stepped_up_at is not None and utcnow() - ctx.stepped_up_at <= auth.STEP_UP_TTL
    return {
        "person_id": person.id,
        "name": person.name,
        "roles": person.roles,
        "aal": ctx.aal,
        "method": ctx.method,
        "stepped_up": fresh,
        "mfa": auth.has_mfa(session, person),
        "pin": auth.has_pin(session, person),
    }


# ---- enrolment links (bootstrap, invites, resets) -----------------------------------------

ENROL_PAGE = """<!doctype html><meta charset="utf-8"><title>Mia</title>
<body style="font-family:system-ui;max-width:28rem;margin:4rem auto">
<h1>Mia</h1><p>Continue to set up your sign-in.</p>
<form method="post"><button style="padding:.6rem 1.2rem">Continue</button></form>
<script>document.forms[0].onsubmit = async (e) => { e.preventDefault();
 const r = await fetch(location.pathname, {method: "POST", headers: {"X-Mia-Client": "web"}});
 location.href = r.ok ? "/" : location.pathname + "?failed=1"; };</script>"""


@router.get("/enrol/{code}", response_class=HTMLResponse)
def enrol_page(code: str) -> str:
    """One button, so previews and scanners that fetch the link do not consume it."""
    return ENROL_PAGE


@router.post("/enrol/{code}", response_model=TokensOut)
def enrol(request: Request, response: Response, session: DbSession, code: str) -> TokensOut:
    """Consume an enrolment link: an enrolment session that can set a password and TOTP."""
    now = utcnow()
    found = auth.check_code(session, "enrol", code, now)
    if found.status != "ok" or found.row is None:
        raise _invalid()
    person = session.get(Person, found.row.person_id)
    if person is None or person.status != "active":
        raise _invalid()
    auth.use_code(session, Actor.person(person), found.row, now)
    tokens = auth.issue_session(
        session, person, method="enrol", aal="enrol", ip=client_ip(request), now=now
    )
    return _tokens_response(request, response, tokens)


# ---- staff: phone code, bound devices, login links ---------------------------------------


class PhoneIn(BaseModel):
    phone: str = Field(max_length=30)


class DeviceIn(BaseModel):
    name: str = Field(max_length=80)
    platform: str = Field(max_length=20)


class OtpVerifyIn(BaseModel):
    phone: str = Field(max_length=30)
    code: str = Field(max_length=6)
    device: DeviceIn


class DeviceLoginIn(BaseModel):
    device_id: str = Field(max_length=26)
    device_secret: str = Field(max_length=100)


@router.post("/otp/start")
def otp_start(session: DbSession, body: PhoneIn) -> dict[str, bool]:
    """Send a sign-in code to the number's WhatsApp. The answer never says whether the
    number is known."""
    auth.send_otp(session, body.phone, utcnow())
    return {"ok": True}


@router.post("/otp/verify")
def otp_verify(
    request: Request, response: Response, session: DbSession, body: OtpVerifyIn
) -> dict[str, object]:
    """Check the code, bind the device and sign in (aal1). The device secret is shown once."""
    now, ip = utcnow(), client_ip(request)
    try:
        person = auth.check_otp(session, body.phone, body.code, ip, now)
    except auth.AuthError:
        raise _invalid() from None
    actor = Actor.person(person)
    name = f"{body.device.name} ({body.device.platform})"
    device, secret = auth.bind_device(session, actor, person, "mobile", name, now)
    tokens = auth.issue_session(
        session, person, method="phone_otp", aal="aal1", ip=ip, now=now, device=device
    )
    out = _tokens_response(request, response, tokens).model_dump()
    out.update({"device_id": device.id, "device_secret": secret})
    return out


@router.post("/device", response_model=TokensOut)
def device_login(
    request: Request, response: Response, session: DbSession, body: DeviceLoginIn
) -> TokensOut:
    """Sign in on a bound device with its secret (aal1; the PIN steps it up)."""
    now, ip = utcnow(), client_ip(request)
    try:
        device = auth.check_device(session, body.device_id, body.device_secret, ip, now)
    except auth.AuthError:
        raise _invalid() from None
    person = session.get(Person, device.person_id)
    if person is None or person.status != "active":
        raise _invalid()
    tokens = auth.issue_session(
        session, person, method="device", aal="aal1", ip=ip, now=now, device=device
    )
    return _tokens_response(request, response, tokens)


LINK_PAGE = """<!doctype html><meta charset="utf-8"><title>Mia</title>
<body style="font-family:system-ui;max-width:28rem;margin:4rem auto"><h1>Mia</h1>
<form method="post"><button style="padding:.6rem 1.2rem">Continue as {name}</button></form>
<script>document.forms[0].onsubmit = async (e) => { e.preventDefault();
 const r = await fetch(location.pathname, {method: "POST", headers: {"X-Mia-Client": "web"}});
 location.href = r.ok ? "/" : location.pathname + "?failed=1"; };</script>"""


def _link_person(session: Session, code: str) -> tuple[Person, AuthCode] | None:
    found = auth.check_code(session, "link_login", code, utcnow())
    if found.status != "ok" or found.row is None:
        return None
    person = session.get(Person, found.row.person_id)
    if person is None or person.status != "active":
        return None
    return person, found.row


@router.get("/link/{code}", response_class=HTMLResponse)
def link_page(session: DbSession, code: str) -> str:
    """The login link's page: one button, so fetching the URL never consumes the link."""
    found = _link_person(session, code)
    if found is None:
        raise HTTPException(404, "link expired or already used")
    return LINK_PAGE.replace("{name}", html.escape(found[0].name.split()[0]))


@router.post("/link/{code}", response_model=TokensOut)
def link_login(request: Request, response: Response, session: DbSession, code: str) -> TokensOut:
    """Consume the login link: a browser device and an aal1 session."""
    found = _link_person(session, code)
    if found is None:
        raise _invalid()
    person, row = found
    now, ip = utcnow(), client_ip(request)
    actor = Actor.person(person)
    auth.use_code(session, actor, row, now)
    agent = request.headers.get("user-agent", "browser")[:80]
    device, _ = auth.bind_device(session, actor, person, "browser", agent, now)
    tokens = auth.issue_session(
        session, person, method="wa_link", aal="aal1", ip=ip, now=now, device=device
    )
    return _tokens_response(request, response, tokens)


# ---- PIN and step-up ---------------------------------------------------------------------


class PinIn(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


def _may_set_pin(ctx: AuthContext) -> bool:
    return ctx.aal == "aal2" or ctx.method == "phone_otp"


@router.post("/pin")
def set_pin(session: DbSession, ctx: PersonAuth, body: PinIn) -> dict[str, bool]:
    """Set the 6-digit PIN from an aal2 session, or on a bound device right after a phone
    code. Trivial PINs are refused (400)."""
    if not _may_set_pin(ctx):
        raise HTTPException(403, "an MFA login or a fresh phone code is needed to set the PIN")
    try:
        auth.set_pin(session, ctx.actor, _person(ctx), body.pin, utcnow())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@router.post("/stepup")
def stepup(request: Request, session: DbSession, ctx: PersonAuth, body: PinIn) -> dict[str, bool]:
    """Enter the PIN: the session counts as stepped up for five minutes."""
    now = utcnow()
    try:
        ok = auth.check_pin(session, _person(ctx), body.pin, client_ip(request), now)
    except auth.Locked:
        raise HTTPException(401, "pin locked") from None
    if not ok:
        raise _invalid()
    row = session.get(AuthSession, ctx.session_id) if ctx.session_id else None
    if row is None:
        raise HTTPException(403, "no session to step up")
    auth.step_up(session, row, now)
    return {"stepped_up": True}


# ---- clients: OAuth2 client credentials (RFC 6749 section 4.4) -------------------------


def _form(body: bytes) -> dict[str, str]:
    """application/x-www-form-urlencoded, parsed with the standard library (no form dependency)."""
    return {k: v[0] for k, v in parse_qs(body.decode(errors="replace")).items()}


def _client_error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status, headers={"Cache-Control": "no-store"})


@router.post("/token")
async def token(request: Request, session: DbSession) -> JSONResponse:
    """Client credentials grant: HTTP Basic or form credentials, a one-hour opaque bearer
    token, no refresh. Errors follow RFC 6749 section 5.2."""
    form = _form(await request.body())
    if form.get("grant_type") != "client_credentials":
        return _client_error("unsupported_grant_type", 400)
    client_id, client_secret = form.get("client_id"), form.get("client_secret")
    basic = request.headers.get("authorization", "")
    if basic.lower().startswith("basic "):
        try:
            client_id, client_secret = base64.b64decode(basic[6:]).decode().split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return _client_error("invalid_client", 401)
    if not client_id or not client_secret:
        return _client_error("invalid_client", 401)
    now, ip = utcnow(), client_ip(request)
    try:
        client = auth.check_client(session, client_id, client_secret, ip, now)
    except auth.AuthError:
        return _client_error("invalid_client", 401)
    tokens = auth.issue_session(session, client, method="client", aal="client", ip=ip, now=now)
    return JSONResponse(
        {
            "access_token": tokens.access,
            "token_type": "Bearer",
            "expires_in": int(auth.CLIENT_TTL.total_seconds()),
        },
        headers={"Cache-Control": "no-store"},
    )
