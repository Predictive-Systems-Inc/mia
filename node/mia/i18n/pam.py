"""Kapampangan strings. Machine drafts until a native speaker reviews them (docs/questions.md)."""

STRINGS: dict[str, str | list[str]] = {
    "agent.shift_supervisor.label": "Shift Supervisor",
    "agent.sales_supervisor.label": "Sales Supervisor",
    "agent.inventory_manager.label": "Inventory Manager",
    "agent.bookkeeper.label": "Bookkeeper",
    "agent.hr_officer.label": "HR Officer",
    "agent.branch_manager.label": "Branch Manager",
    "chat.switched": "({agent})",
    "route.question": "Tungkul ba ini king:",
    "reply.busy": [
        "Mapagobra ya o ngeni si Mia at sasagutan daka na mamaya.",
        "Mapagobra ya o ngeni si Mia. Sasagutan daka na mekawani.",
    ],
    "reply.no_agent": (
        "Alang pa akung maitulung keka keni. Sabyan mu ing supervisor mu a i-set up ya si Mia para keka."
    ),
    "reply.unavailable": [
        "Pasensya, e ku makasagut ngeni. Pakiulit pa mamaya.",
        "Pasensya, atin mengaproblema keng bandi ku. Pakiulit pa mekawani.",
    ],
    "reply.not_built": "E pa ini asaupan nang Mia.",
    "cli.learned.none": "Alang pa ya naaldwa a ruta ni Mia keni.",
    "cli.learned.row": "{agent}\t{route}\t{count}",
    "cli.forgotten": "Limutan na: {route}",
    "language.set": "Sige, {language} ing gamitan ku.",
}
