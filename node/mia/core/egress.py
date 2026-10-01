"""Cloud egress: the single exit for anything sent to a cloud model.

send() applies the organisation's level before anything leaves: `none` raises EgressBlocked
before any network call; `pseudonymised` replaces person names with stable tokens (Person_<n>),
keeping the token-to-name mapping on the node. Every allowed request is written to egress_log
with a hash of the outgoing payload. EgressTransport plugs this into the HTTP client used by the
model provider, so model code never talks to the network directly.
"""

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlmodel import Session, col, select

from mia.core import store, usage
from mia.core.models import Actor, EgressLog, Person

LEVELS = ("none", "pseudonymised")


class EgressBlocked(Exception):
    """The organisation's policy does not allow this request to leave the node."""


@dataclass
class Pseudonymiser:
    """Maps person names to tokens and back. Stable per branch: Person_<n> follows id order."""

    names: dict[str, str] = field(default_factory=dict)  # name -> token

    @classmethod
    def for_branch(cls, session: Session, branch_id: str) -> "Pseudonymiser":
        persons = session.exec(
            select(Person).where(Person.branch_id == branch_id).order_by(col(Person.id))
        ).all()
        names: dict[str, str] = {}
        for n, person in enumerate(persons, start=1):
            token = f"Person_{n}"
            names[person.name] = token
            for part in person.name.split():
                names.setdefault(part, token)
        return cls(names)

    def _pattern(self) -> re.Pattern[str] | None:
        if not self.names:
            return None
        alternatives = sorted(self.names, key=len, reverse=True)
        return re.compile(
            r"\b(" + "|".join(map(re.escape, alternatives)) + r")(\w*)", re.IGNORECASE
        )

    def apply(self, text: str) -> str:
        """Replace names (and inflected forms such as 'Mikaelin') with tokens."""
        pattern = self._pattern()
        if pattern is None:
            return text
        lookup = {k.lower(): v for k, v in self.names.items()}

        def repl(m: re.Match[str]) -> str:
            token = lookup[m.group(1).lower()]
            return f"{token}:{m.group(2)}" if m.group(2) else token

        return pattern.sub(repl, text)

    def restore(self, text: str) -> str:
        """Replace tokens with the full names they stand for."""
        full = {}
        for name, token in self.names.items():
            if " " in name or token not in full:
                full[token] = name
        return re.sub(r"Person_(\d+)", lambda m: full.get(m.group(0), m.group(0)), text)


@dataclass
class EgressContext:
    """Who is sending and why. Set around an agent run; required for any egress."""

    session: Session
    actor: Actor
    organisation_id: str
    agent_id: str
    purpose: str
    level: str
    provider: str = "gateway"


_context: ContextVar[EgressContext | None] = ContextVar("mia_egress_context", default=None)


@contextmanager
def egress_context(ctx: EgressContext) -> Iterator[EgressContext]:
    token = _context.set(ctx)
    try:
        yield ctx
    finally:
        _context.reset(token)


def bind_context(ctx: EgressContext) -> None:
    """Set the context for the rest of the current task (for streamed responses)."""
    _context.set(ctx)


def current_context() -> EgressContext:
    ctx = _context.get()
    if ctx is None:
        raise EgressBlocked("no egress context: nothing leaves the node without one")
    return ctx


def payload_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


def send(
    session: Session,
    purpose: str,
    payload: str,
    level: str,
    *,
    actor: Actor,
    agent_id: str,
    provider: str = "gateway",
    pseudonymise: bool = True,
) -> tuple[str, Pseudonymiser]:
    """Apply the policy to a payload and log it. Returns what may leave plus the mapping.

    Raises EgressBlocked for level `none` (or an unknown level) before any network call.
    `pseudonymise=False` is for payloads that must leave as they are (an address to geocode);
    the request is still blocked by level `none` and still logged.
    """
    if level not in LEVELS or level == "none":
        raise EgressBlocked(f"egress level {level!r} blocks cloud requests")
    pseudo = Pseudonymiser.for_branch(session, actor.branch_id) if pseudonymise else Pseudonymiser()
    outgoing = pseudo.apply(payload)
    store.insert(
        session,
        EgressLog(
            branch_id=actor.branch_id,
            agent_id=agent_id,
            purpose=purpose,
            level=level,
            provider=provider,
            payload_hash=payload_hash(outgoing),
        ),
        actor,
        action="egress.sent",
    )
    return outgoing, pseudo


def _usage_counts(body: dict[str, Any]) -> tuple[int, int]:
    u = body.get("usage") or {}
    return int(u.get("prompt_tokens", 0) or 0), int(u.get("completion_tokens", 0) or 0)


class EgressTransport(httpx.AsyncBaseTransport):
    """httpx transport that sends every request through send() and meters the response.

    Model calls (POST bodies) are pseudonymised and metered in usage_cloud_requests. Service
    calls such as geocoding use `pseudonymise=False, meter=False`; their URL query is what is
    logged, because that is what leaves the node.
    """

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport | None = None,
        *,
        pseudonymise: bool = True,
        meter: bool = True,
    ) -> None:
        self.inner = inner or httpx.AsyncHTTPTransport()
        self.pseudonymise = pseudonymise
        self.meter = meter

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        ctx = current_context()
        raw = (await request.aread()).decode()
        outgoing, pseudo = send(
            ctx.session,
            ctx.purpose,
            raw or request.url.query.decode(),
            ctx.level,
            actor=ctx.actor,
            agent_id=ctx.agent_id,
            provider=ctx.provider,
            pseudonymise=self.pseudonymise,
        )
        headers = {k: v for k, v in request.headers.items() if k.lower() != "content-length"}
        body = outgoing if raw else b""
        forwarded = httpx.Request(request.method, request.url, headers=headers, content=body)
        response = await self.inner.handle_async_request(forwarded)
        content = (await response.aread()).decode()
        if self.meter:
            self._record_usage(ctx, response.status_code, content)
        resp_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")
        }
        return httpx.Response(
            response.status_code,
            headers=resp_headers,
            content=pseudo.restore(content).encode(),
            request=request,
        )

    @staticmethod
    def _record_usage(ctx: EgressContext, status_code: int, content: str) -> None:
        model = "unknown"
        result = "success" if status_code < 400 else "error"
        input_tokens = output_tokens = 0
        try:
            body = json.loads(content)
            model = str(body.get("model", model))
            input_tokens, output_tokens = _usage_counts(body)
        except ValueError:
            pass
        usage.record(
            ctx.session,
            ctx.actor,
            organisation_id=ctx.organisation_id,
            agent_id=ctx.agent_id,
            task=ctx.purpose,
            model=model,
            provider=ctx.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            result=result,
        )
