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
    "sales_supervisor": (
        "Sales: clerks reporting how many of each item they sold, daily and mid-day sales"
        " totals, sales targets, how today's sales compare, why sales went well, selling tips"
        " and sales experiments."
    ),
    "inventory_manager": (
        "Stock: items sold out or running low, how many are left, leftovers and waste at"
        " closing, what to prepare or bake tomorrow, ordering from suppliers."
    ),
    "bookkeeper": (
        "Money: the cash count against sales, expenses and receipts, bank deposits, VAT and"
        " BIR records."
    ),
    "hr_officer": (
        "Employment: hours worked, payroll and payslips, 13th month pay, leave balances,"
        " SSS, PhilHealth and Pag-IBIG contributions."
    ),
    "branch_manager": (
        "Running the shop: branches, the menu, prices and item short codes, people and their"
        " roles, the weekly summary."
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
    """The unavailable reply; nothing else runs."""
    text = t("reply.unavailable", turn.deps.lang)
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
