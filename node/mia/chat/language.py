"""The reply language: asked once, then kept until the person asks to change it (ADR 016).

Nothing detects the language of a message; every reply uses person.language."""

from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.chat.blocks import ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import latest_message, store_reply
from mia.core import events, orgconfig
from mia.core.models import Event, Message, Person, Thread
from mia.i18n import t

CHANGE_WORDS = frozenset({"language", "wika", "pinulongan", "lengguahe"})
ASKED = "language.asked"


def is_change_command(text: str) -> bool:
    """True for the exact change words, any case, with or without a leading slash."""
    return text.strip().lstrip("/").strip().casefold() in CHANGE_WORDS


def _offered() -> list[str]:
    return list(orgconfig.load().languages)


def offers_choice() -> bool:
    """The organisation offers two or more languages (otherwise nobody is asked and the change
    words are ordinary text)."""
    return len(_offered()) >= 2


def needs_asking(session: Session, person: Person) -> bool:
    """The organisation offers a choice and the person never chose one."""
    if not offers_choice():
        return False
    chosen = session.exec(
        select(Event)
        .where(Event.action == "person.language_chosen")
        .where(Event.entity_id == person.id)
    ).first()
    return chosen is None


def ask(
    session: Session, deps: AgentDeps, thread: Thread, original_message_id: str | None
) -> ChatReply:
    """The language question with one button per offered language, each named in itself.
    With original_message_id the message is answered after the tap."""
    options = {t(f"language.name.{code}", "en"): code for code in _offered()}
    reply = store_reply(
        session,
        deps,
        thread,
        [TextBlock(text=t("language.ask", "en")), QuickRepliesBlock(options=list(options))],
    )
    events.emit(
        session,
        ASKED,
        ("thread", thread.id),
        None,
        {
            "options": options,
            "message_id": reply.message_id,
            "original_message_id": original_message_id,
        },
        deps.actor,
    )
    return reply


def tapped(session: Session, thread: Thread, text: str) -> tuple[str, str | None] | None:
    """(language, original message id) when text is a button of the language question that is
    the thread's last Mia message, typed in any case; otherwise None (a stale button is plain
    text)."""
    asked = session.exec(
        select(Event)
        .where(Event.action == ASKED)
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = latest_message(session, thread, "assistant")
    after = (asked.after or {}) if asked is not None else {}
    if last is None or after.get("message_id") != last.id:
        return None
    options = {label.casefold(): code for label, code in (after.get("options") or {}).items()}
    code = options.get(text.strip().casefold())
    return (str(code), after.get("original_message_id")) if code else None


def original_text(session: Session, message_id: str | None) -> str | None:
    """The text of the message the question interrupted, or None."""
    row = session.get(Message, message_id) if message_id else None
    return row.text if row is not None else None
