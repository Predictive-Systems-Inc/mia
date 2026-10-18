"""The roster agents that are not built yet: a label and a router description each, so routing
can be measured before they exist. Their turn says Mia cannot answer that yet. These are the
only agent ids spelled in code (rule 15); built agents take theirs from a manifest."""

import asyncio

from mia.agents.base import AgentSpec, InstructionsSpec, Manifest, RolesSpec, Turn
from mia.chat.blocks import ChatReply
from mia.chat.replies import reply_text
from mia.core.models import STANDARD_VERSION
from mia.i18n import t

DESCRIPTIONS = {
    "bookkeeper": (
        "Money: the cash count against sales, a cash drawer short or over, expenses and"
        " receipts, bank deposits, GCash and Maya sales and settlements, Grab payouts, VAT and"
        " BIR records; not sales counts, not a morning's or day's sales total and not pay."
    ),
    "hr_officer": (
        "Employment: my hours worked this cutoff, cash advances, holiday pay, payroll and"
        " payslips, 13th month pay, leave balances, SSS, PhilHealth and Pag-IBIG contributions,"
        " hiring; not who works which shift and not adding people to a branch."
    ),
    "branch_manager": (
        "Running the shop: branches, the menu and new menu items, prices and item short codes,"
        " who approves what, shop opening hours, people and their roles, permits, the weekly"
        " summary, coaching and tips for staff; not a day's counts and not a shift change."
    ),
}


def _manifest(agent_id: str) -> Manifest:
    """A manifest with no tools and no grants: a stub can do nothing."""
    return Manifest(
        id=agent_id,
        name=agent_id,
        version="0",
        standard_version=STANDARD_VERSION,
        instructions=InstructionsSpec(base=""),
        roles=RolesSpec(agent_role=f"agent.{agent_id}", grants=[]),
        tools=[],
    )


async def _not_built(turn: Turn) -> ChatReply:
    """The not-built reply (retrying never helps); nothing else runs."""
    text = t("reply.not_built", turn.deps.lang)
    return await asyncio.to_thread(reply_text, turn.session, turn.deps, turn.thread, text)


STUBS = [
    AgentSpec(
        manifest=_manifest(agent_id),
        label_key=f"agent.{agent_id}.label",
        router_description=description,
        handle_turn=_not_built,
    )
    for agent_id, description in DESCRIPTIONS.items()
]
