"""The short-message Jev check (D42): twelve short en and twelve short fil messages per Ferino's
agent, as kiosk staff, head staff, the owner, the driver or a customer type on a phone:
lowercase, no punctuation, numbers as digits, abbreviations and code-mixing, one to six words.
Each agent's set covers its main actions and has two deliberately ambiguous messages that should
ask (expected "ask"). The one hard rule (D42) is no wrong write: a decided action that writes a
row and is not the expected one. The real run is test_short_evals.py; test_short_cases.py keeps
the set well formed.

Synthetic, written by Claude, not native speakers (D18). The fil texts are Claude's drafts of
how Filipino staff abbreviate (Q28); the en and fil texts are written separately, not
translations of each other. A case's role is a seeded Ferino's person's role (or "customer",
the seeded customer Mila, for customer_service). Expected arguments (an item code, an amount in
minor units, a number, a date) are relative to TODAY, the pp_shop fixture's day.
"""

import datetime as dt
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from mia.i18n import t
from tests.conftest import PP_TODAY

TODAY = PP_TODAY  # Tuesday 10 November 2026
TOMORROW = TODAY + dt.timedelta(days=1)
YESTERDAY = TODAY - dt.timedelta(days=1)
MONDAY = dt.date(2026, 11, 16)
FRIDAY = dt.date(2026, 11, 13)
SATURDAY = dt.date(2026, 11, 14)

AGENTS = (
    "sales_supervisor",
    "shift_supervisor",
    "inventory_manager",
    "hr_officer",
    "customer_service",
    "branch_manager",
    "bookkeeper",
    "production_planner",
)
LANGS = ("en", "fil")
ASK = "ask"


@dataclass(frozen=True)
class Case:
    lang: str
    agent: str
    text: str
    role: str  # a seeded person's role (owner, supervisor, clerk, staff) or customer
    expected_action: str  # an action of the agent's ACTIONS, or "ask"
    writes: bool  # the expected action writes a row (its tool declares writes)
    item: str = ""  # the item or ingredient code as typed
    amount: int | None = None  # minor units
    number: int | None = None
    date: dt.date | None = None
    previous: str = ""  # Mia's last message in the thread


def actions(agent: str) -> dict[str, Any]:
    """The agent's offered actions (the retail ones for the shift supervisor at Ferino's)."""
    module = import_module(f"mia.agents.{agent}.actions")
    return dict(module.RETAIL_ACTIONS if agent == "shift_supervisor" else module.ACTIONS)


def writes(agent: str, action: str) -> bool:
    """True when the action's tool declares a write in the agent's manifest; "ask", clarify and
    the tool-less actions never write."""
    found = actions(agent).get(action)
    if found is None or found.tool is None:
        return False
    manifest = import_module(f"mia.agents.{agent}").MANIFEST
    return any(tool.name == found.tool and tool.writes for tool in manifest.tools)


W, R = True, False  # writes, reads (or no tool)
WHY_EN, WHY_FIL = t("sales.why", "en"), t("sales.why", "fil")

# (role, text, expected action, writes, the expected arguments)
ROWS: dict[tuple[str, str], list[tuple[str, str, str, bool, dict[str, Any]]]] = {
    ("sales_supervisor", "en"): [
        ("clerk", "sp 5 cl 8 ube 3", "report_sales", W, {"item": "sp", "number": 5}),
        ("clerk", "ube 7 se 4", "report_sales", W, {"item": "ube", "number": 7}),
        ("clerk", "sorry cl 6 not 8", "correct_sales", W, {"item": "cl", "number": 6}),
        ("supervisor", "sales so far", "sales_today", R, {}),
        ("owner", "how much today mall", "sales_today", R, {}),
        ("owner", "sales yday", "sales_period", R, {"date": YESTERDAY}),
        ("owner", "best day this wk", "sales_period", R, {}),
        ("owner", "target 4500 tmrw", "set_target", W, {"amount": 450000, "date": TOMORROW}),
        ("supervisor", "payday crowd", "why_answer", W, {"previous": WHY_EN}),
        ("clerk", "thx mia", "reply_only", R, {}),
        ("clerk", "cl 8 or 9", ASK, R, {"item": "cl"}),
        ("clerk", "ube pls", ASK, R, {"item": "ube"}),
    ],
    ("sales_supervisor", "fil"): [
        ("clerk", "cl 10 sp 4 ube 6", "report_sales", W, {"item": "cl", "number": 10}),
        ("clerk", "benta ko 5 se 3 co", "report_sales", W, {"item": "se", "number": 5}),
        ("clerk", "mali pala ube 4 dapat", "correct_sales", W, {"item": "ube", "number": 4}),
        ("supervisor", "kumusta benta ngayon", "sales_today", R, {}),
        ("owner", "magkano na tayo today", "sales_today", R, {}),
        ("owner", "benta kahapon street", "sales_period", R, {"date": YESTERDAY}),
        ("owner", "benta nung isang linggo", "sales_period", R, {}),
        ("owner", "target bukas 5000", "set_target", W, {"amount": 500000, "date": TOMORROW}),
        ("supervisor", "sweldo kasi dami tao", "why_answer", W, {"previous": WHY_FIL}),
        ("clerk", "sige tnx po", "reply_only", R, {}),
        ("clerk", "ube pa", ASK, R, {"item": "ube"}),
        ("supervisor", "yung kahapon", ASK, R, {}),
    ],
    ("shift_supervisor", "en"): [
        ("clerk", "late 15m traffic", "record_absence", W, {"date": TODAY}),
        ("clerk", "sick tmrw cant come", "record_absence", W, {"date": TOMORROW}),
        ("clerk", "here now opening", "check_in", W, {}),
        ("clerk", "done going home", "check_out", W, {}),
        ("clerk", "my sched tmrw", "get_my_visits", R, {"date": TOMORROW}),
        ("supervisor", "roster this wk", "week_roster", R, {}),
        ("supervisor", "who can cover ana tmrw", "find_replacements", R, {"date": TOMORROW}),
        ("clerk", "swap w liza fri", "swap", W, {"date": FRIDAY}),
        ("clerk", "forgot time out left 9pm", "correct_time", W, {}),
        ("clerk", "oven broken", "report_site_problem", W, {}),
        ("clerk", "liza fri", ASK, R, {}),
        ("clerk", "9pm", ASK, R, {}),
    ],
    ("shift_supervisor", "fil"): [
        ("clerk", "late ako 10 mins", "record_absence", W, {"date": TODAY}),
        ("clerk", "masakit ulo ko absent muna", "record_absence", W, {"date": TODAY}),
        ("clerk", "andito na me sa kiosk", "check_in", W, {}),
        ("clerk", "out na ko tnx", "check_out", W, {}),
        ("clerk", "sched ko bukas", "get_my_visits", R, {"date": TOMORROW}),
        ("supervisor", "sino pwede kay ana bukas", "find_replacements", R, {"date": TOMORROW}),
        ("clerk", "palit kami ni liza sab", "swap", W, {"date": SATURDAY}),
        ("clerk", "nakalimutan ko time out 9pm", "correct_time", W, {}),
        ("clerk", "sira ref", "report_site_problem", W, {}),
        ("supervisor", "sarado mall sa sabado", "close_day", W, {"date": SATURDAY}),
        ("clerk", "bukas po", ASK, R, {}),
        ("clerk", "liza po", ASK, R, {}),
    ],
    ("inventory_manager", "en"): [
        ("clerk", "ube 5 left", "report_stock", W, {"item": "ube", "number": 5}),
        ("clerk", "sold out cl", "report_stock", W, {"item": "cl"}),
        ("clerk", "3 sp thrown burnt", "report_stock", W, {"item": "sp", "number": 3}),
        ("clerk", "eggs low 1 tray", "report_stock", W, {"item": "eggs", "number": 1}),
        ("supervisor", "what to bake tmrw", "bake_plan", R, {}),
        ("supervisor", "whats low", "whats_low", R, {}),
        ("supervisor", "need to order anything", "whats_low", R, {}),
        ("owner", "order 10 trays eggs", "place_order", W, {"item": "eggs", "number": 10}),
        ("supervisor", "buy 5 kg flour", "place_order", W, {"item": "flour", "number": 5}),
        ("clerk", "delivery came 30 coco", "receive", W, {"item": "coco", "number": 30}),
        ("clerk", "ube", ASK, R, {"item": "ube"}),
        ("clerk", "eggs 10", ASK, R, {"item": "eggs", "number": 10}),
    ],
    ("inventory_manager", "fil"): [
        ("clerk", "5 ube nlng", "report_stock", W, {"item": "ube", "number": 5}),
        ("clerk", "ubos na cl", "report_stock", W, {"item": "cl"}),
        ("clerk", "2 sp tapon sunog", "report_stock", W, {"item": "sp", "number": 2}),
        ("clerk", "konti nlng itlog", "report_stock", W, {"item": "itlog"}),
        ("supervisor", "ilan gagawin bukas", "bake_plan", R, {}),
        ("supervisor", "ano kulang sa stock", "whats_low", R, {}),
        ("supervisor", "may ioorder ba tayo", "whats_low", R, {}),
        ("owner", "bili 10 tray itlog", "place_order", W, {"item": "itlog", "number": 10}),
        ("supervisor", "order 3 lpg pls", "place_order", W, {"item": "lpg", "number": 3}),
        ("clerk", "dumating na 20 niyog", "receive", W, {"item": "niyog", "number": 20}),
        ("clerk", "itlog po", ASK, R, {"item": "itlog"}),
        ("clerk", "ilan pa ube", ASK, R, {"item": "ube"}),
    ],
    ("hr_officer", "en"): [
        ("clerk", "my hrs this cutoff", "my_hours", R, {}),
        ("clerk", "when payday", "payday", R, {}),
        ("clerk", "13th month how much", "thirteenth", R, {}),
        ("clerk", "sss deduction last pay", "contributions", R, {}),
        ("clerk", "vl dec 2 to 3", "file_leave", W, {"date": dt.date(2026, 12, 2)}),
        ("clerk", "sick leave tmrw pls", "file_leave", W, {"date": TOMORROW}),
        ("clerk", "leave left", "leave_balance", R, {}),
        ("clerk", "holiday pay nov 30", "holiday_pay", R, {"date": dt.date(2026, 11, 30)}),
        ("clerk", "resend payslip pls", "my_payslip", W, {}),
        ("owner", "need coe ana", "certificate", R, {}),
        ("clerk", "cutoff", ASK, R, {}),
        ("clerk", "nov 30", ASK, R, {"date": dt.date(2026, 11, 30)}),
    ],
    ("hr_officer", "fil"): [
        ("clerk", "ilang oras ko ngayong cutoff", "my_hours", R, {}),
        ("clerk", "kelan sweldo natin", "payday", R, {}),
        ("clerk", "magkano 13th month ko", "thirteenth", R, {}),
        ("clerk", "philhealth kaltas ko", "contributions", R, {}),
        ("clerk", "pa file vl biyernes", "file_leave", W, {"date": FRIDAY}),
        ("clerk", "day off ako sab pls", "file_leave", W, {"date": SATURDAY}),
        ("clerk", "ilan pa leave ko", "leave_balance", R, {}),
        ("clerk", "holiday ba lunes", "holiday_pay", R, {"date": MONDAY}),
        ("clerk", "payslip ko po ulit", "my_payslip", W, {}),
        ("owner", "pa coe kay liza", "certificate", R, {}),
        ("clerk", "sahod", ASK, R, {}),
        ("clerk", "leave po", ASK, R, {}),
    ],
    ("customer_service", "en"): [
        ("customer", "open now", "hours", R, {}),
        ("customer", "what time u close", "hours", R, {}),
        ("customer", "how much ube", "prices", R, {"item": "ube"}),
        ("customer", "menu pls", "prices", R, {}),
        ("customer", "order 10 classic pickup 3pm", "place_order", W, {"item": "classic"}),
        ("customer", "is my order ready", "order_status", R, {}),
        ("customer", "deliver to marikina", "delivery_area", R, {}),
        ("customer", "bibingka was cold", "complaint", W, {}),
        ("customer", "cancel my order pls", "cancel_order", W, {}),
        ("clerk", "pickups today", "staff_orders_today", R, {}),
        ("customer", "10 ube", ASK, R, {"item": "ube", "number": 10}),
        ("customer", "tmrw 3pm", ASK, R, {"date": TOMORROW}),
    ],
    ("customer_service", "fil"): [
        ("customer", "open pa kau ngayon", "hours", R, {}),
        ("customer", "hm po ung special", "prices", R, {"item": "special"}),
        ("customer", "pa order 12 cl bukas", "place_order", W, {"item": "cl", "number": 12}),
        ("customer", "ready na order ko", "order_status", R, {}),
        ("customer", "may deliver sa pasig", "delivery_area", R, {}),
        ("customer", "kulang order ko 2", "complaint", W, {}),
        ("customer", "cancel ko na po", "cancel_order", W, {}),
        ("customer", "english pls", "language_switch", R, {}),
        ("clerk", "may pickup ba today", "staff_orders_today", R, {}),
        ("clerk", "ready na kay mila", "staff_mark_ready", W, {}),
        ("customer", "pano po", ASK, R, {}),
        ("customer", "yung order", ASK, R, {}),
    ],
    ("branch_manager", "en"): [
        ("owner", "how is ana doing", "coaching_who", R, {}),
        ("owner", "who needs coaching", "coaching_who", R, {}),
        ("supervisor", "tips to sell more sp", "how_to_sell", W, {"item": "sp"}),
        (
            "owner",
            "try classic 49 1 wk",
            "propose_experiment",
            W,
            {"item": "classic", "amount": 4900},
        ),
        ("owner", "hows the promo", "experiment_status", R, {}),
        ("owner", "keep new price", "decide_experiment_result", W, {}),
        (
            "owner",
            "classic 48 from monday",
            "change_price",
            W,
            {"item": "classic", "amount": 4800, "date": MONDAY},
        ),
        ("owner", "use ch for overload", "set_short_code", W, {"item": "overload"}),
        ("owner", "week numbers pls", "weekly_summary", R, {}),
        ("owner", "this month vs last", "monthly_letter", R, {}),
        ("owner", "classic 48", ASK, R, {"item": "classic", "amount": 4800}),
        ("owner", "ube price", ASK, R, {"item": "ube"}),
    ],
    ("branch_manager", "fil"): [
        ("owner", "kmusta benta ni liza", "coaching_who", R, {}),
        ("owner", "sino mahina sa team", "coaching_who", R, {}),
        ("supervisor", "pano mabenta ube", "how_to_sell", W, {"item": "ube"}),
        (
            "owner",
            "subukan 45 sp ngayong linggo",
            "propose_experiment",
            W,
            {"item": "sp", "amount": 4500},
        ),
        ("owner", "ok ba yung test", "experiment_status", R, {}),
        ("owner", "balik sa dati presyo", "decide_experiment_result", W, {}),
        (
            "owner",
            "gawing 52 se simula lunes",
            "change_price",
            W,
            {"item": "se", "amount": 5200, "date": MONDAY},
        ),
        ("owner", "gawin bx code ng box", "set_short_code", W, {"item": "box"}),
        ("owner", "benta ngayong linggo vs target", "weekly_summary", R, {}),
        ("owner", "report ng buwan pls", "monthly_letter", R, {}),
        ("owner", "sp 45", ASK, R, {"item": "sp", "amount": 4500}),
        ("owner", "presyo", ASK, R, {}),
    ],
    ("bookkeeper", "en"): [
        ("supervisor", "cash count 9870", "cash_count", W, {"amount": 987000}),
        ("supervisor", "drawer 15200 closing", "cash_count", W, {"amount": 1520000}),
        ("supervisor", "gcash 3210 yday", "settlement", W, {"amount": 321000, "date": YESTERDAY}),
        ("owner", "maya in 1850", "settlement", W, {"amount": 185000}),
        ("owner", "grab payout 8900", "payout", W, {"amount": 890000}),
        ("owner", "foodpanda sent 4300", "payout", W, {"amount": 430000}),
        ("supervisor", "paid electric 2300", "expense", W, {"amount": 230000}),
        ("supervisor", "petty 150 ice", "petty_cash", W, {"amount": 15000}),
        ("owner", "deposited 20000 bdo", "deposit", W, {"amount": 2000000}),
        ("owner", "petty cash left", "balances", R, {}),
        ("supervisor", "12450", ASK, R, {"amount": 1245000}),
        ("owner", "gcash", ASK, R, {}),
    ],
    ("bookkeeper", "fil"): [
        ("supervisor", "bilang pera 11300", "cash_count", W, {"amount": 1130000}),
        ("supervisor", "closing 13250 po", "cash_count", W, {"amount": 1325000}),
        (
            "supervisor",
            "pasok gcash 2780 kahapon",
            "settlement",
            W,
            {"amount": 278000, "date": YESTERDAY},
        ),
        ("owner", "nag remit grab 7650", "payout", W, {"amount": 765000}),
        ("supervisor", "bayad kuryente 2100", "expense", W, {"amount": 210000}),
        ("supervisor", "bayad sa tubero 800", "expense", W, {"amount": 80000}),
        ("supervisor", "petty 200 pamasahe", "petty_cash", W, {"amount": 20000}),
        ("supervisor", "dagdag petty 1000", "petty_cash", W, {"amount": 100000}),
        ("owner", "deposito 15000 bpi", "deposit", W, {"amount": 1500000}),
        ("owner", "kita ng oktubre", "profit", R, {}),
        ("supervisor", "3200 kahapon", ASK, R, {"amount": 320000, "date": YESTERDAY}),
        ("owner", "bayad na", ASK, R, {}),
    ],
    ("production_planner", "en"): [
        ("supervisor", "plan tmrw", "plan", R, {"date": TOMORROW}),
        ("supervisor", "add 1 batch ube", "change_plan", W, {"item": "ube", "number": 1}),
        ("supervisor", "less classic 2 batch", "change_plan", W, {"item": "classic", "number": 2}),
        ("owner", "plan ok go", "confirm_plan", W, {}),
        ("supervisor", "batch sheet sp", "batch_sheet", R, {"item": "sp"}),
        ("supervisor", "batch2 cl 45 ok 3 burnt", "record_batch", W, {"item": "cl"}),
        ("supervisor", "recipe ube 36 pcs 2kg flour", "set_recipe", W, {"item": "ube"}),
        ("staff", "delivered mall", "delivered", W, {}),
        ("clerk", "whats coming to mall", "dispatch", R, {}),
        (
            "owner",
            "capacity 200 cl dec 24",
            "capacity",
            R,
            {"item": "cl", "number": 200, "date": dt.date(2026, 12, 24)},
        ),
        ("supervisor", "ube 2", ASK, R, {"item": "ube", "number": 2}),
        ("staff", "done", ASK, R, {}),
    ],
    ("production_planner", "fil"): [
        ("supervisor", "ano lutuin bukas", "plan", R, {"date": TOMORROW}),
        ("supervisor", "dagdag 1 batch se", "change_plan", W, {"item": "se", "number": 1}),
        ("supervisor", "bawas ube 1 batch", "change_plan", W, {"item": "ube", "number": 1}),
        ("owner", "sige go na plano", "confirm_plan", W, {}),
        ("supervisor", "ilang itlog para sa cl", "batch_sheet", R, {"item": "cl"}),
        ("supervisor", "batch1 sp 40 ok 2 sunog", "record_batch", W, {"item": "sp"}),
        ("supervisor", "recipe se 36 piraso 45 min", "set_recipe", W, {"item": "se"}),
        ("staff", "hatid na sa street po", "delivered", W, {}),
        ("clerk", "ano dadalhin samin bukas", "dispatch", R, {"date": TOMORROW}),
        (
            "owner",
            "kaya ba 150 ube sab",
            "capacity",
            R,
            {"item": "ube", "number": 150, "date": SATURDAY},
        ),
        ("supervisor", "classic 3", ASK, R, {"item": "classic", "number": 3}),
        ("staff", "ok na po", ASK, R, {}),
    ],
}

CASES: list[Case] = [
    Case(lang, agent, text, role, action, w, **kw)
    for (agent, lang), rows in ROWS.items()
    for role, text, action, w, kw in rows
]
