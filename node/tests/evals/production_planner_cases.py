"""The production planner decider eval set (spec 2026-10-21-production-planner, scenarios 1 to 7
and 9 as chat asks): what the commissary head, the owner, the driver and a kiosk supervisor
send, in each gated language. Data only; test_production_planner_evals.py runs it.

Two sets. The spent rows (the lists named after their scenario, PLAN to CAPACITY) were scored by
the 0747 tune and 0748 gate runs and are kept only as a record: half "spent", never selected.
The fresh rows (FRESH, written for the D40 rerun) are ten per scenario, halves by seed: the
even seeds of a scenario are the tune half, the odd seeds the gate half, and a seed's languages
share a half (no text in both halves, and no fresh text in a spent row or either raw file of
the earlier runs, shape test). They cover the intents the 0748 run got wrong or asked on with
other words: the dispatch texts name the delivery or the dispatch (so "how many pieces are we
getting" is not the plan question), the batch sheet asks name one item (an ingredient word is
never an item), and each change states its unit, its number and, for more or fewer, an add or
remove word of the language (the guards ask a change without a unit and never let an add or
remove word set; words.directions and words.units, shape test).

Scenario 1 is two asks (the plan, and "ok" answering the draft plan), scenario 7 two (a kiosk
supervisor asking what the delivery brings and the driver's delivered); scenario 2 (confirmed
orders in the plan) is asked as the plan. The draft plan Mia sent before every confirm (DRAFT)
is built from the reply keys (pp.plan.*), so it reads as the real reply in each language.

Synthetic, written by Claude, not native speakers (D18). English seeds come first; the five
Philippine languages are drafts for commissary and kiosk staff texting on a phone, and Q28 to
Q35 cover their review. The run pins today to TODAY (PP_TODAY, a Tuesday) with tomorrow's plan
drafted, so "bukas", "ugma", "buwas" and "sa aga" name the plan's date. Code reads every value
Jev picks (rule 7), and the shape test checks it: each expected number is a words.numbers
candidate, each batch report a words.batch parse, each recipe a full words.recipe parse (one
part per comma, units and short codes code knows), each added or removed item a line of the
drafted plan, and each fresh item ask names that one item (words.named). No change text names
"today" (subong, karon, yana), which would ask for the plan of another day.

The short half (SHORT, D42): twelve en and twelve fil messages as the commissary head, the
owner, the driver and a kiosk clerk type on a phone (lowercase, no punctuation, digits, one to
six words), the en and fil written apart, not translations; two per language are ambiguous and
should ask ("ask"). Its one rule is no wrong write (gate.wrong_writes); its expected item and
number are reported, never a bar."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

from mia.i18n import t


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str  # an ACTIONS key
    # head (Nonoy, the commissary), owner (Rosa), driver (Berto), kiosk (Marites), clerk (Ana)
    role: str
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "gate", "spent", "short"] = "tune"  # spent: scored, never run again
    # item (an item name), kiosk (a branch name), direction (a DIRECTIONS key), number (a count)
    expected: dict[str, Any] = field(default_factory=dict)


GATED_LANGS = ("en", "fil", "ceb", "hil", "war", "bcl")
TODAY = dt.date(2026, 11, 10)  # a Tuesday, PP_TODAY

Row = tuple[dict[str, Any], str, str, str, str, str, str]  # expected, then en fil ceb hil war bcl
NONE: dict[str, Any] = {}


def _i(item: str, **more: Any) -> dict[str, Any]:
    return {"item": item, **more}


def _ch(item: str, direction: str, number: int) -> dict[str, Any]:
    return {"item": item, "direction": direction, "number": number}


PLAN: list[Row] = [
    (NONE, "what are we baking tomorrow?", "ano ang lulutuin natin bukas?",
     "unsa among lutuon ugma?", "ano ang lutuon naton buwas?", "ano an aton lulutuon buwas?",
     "ano an lulutoon ta sa aga?"),
    (NONE, "send me tomorrow's production plan", "ipadala ang production plan para bukas",
     "ipadala ang production plan para ugma", "ipadala ang production plan para buwas",
     "ipadara an production plan para buwas", "ipadara an production plan para sa aga"),
    (NONE, "how many batches of each item tomorrow?", "ilang batch bawat item bukas?",
     "pila ka batch matag item ugma?", "pila ka batch kada item buwas?",
     "pira nga batch kada item buwas?", "pirang batch kada item sa aga?"),
    (NONE, "show me the plan", "patingin ng plano", "ipakita ang plano",
     "ipakita ang plano sa akon", "ipakita an plano", "ipahiling an plano"),
    (NONE, "what's in the plan for Wednesday?", "ano ang nasa plano sa Miyerkules?",
     "unsa ang naa sa plano sa Miyerkules?", "ano ang yara sa plano sa Miyerkoles?",
     "ano an aadi ha plano ha Miyerkoles?", "ano an yaon sa plano sa Miyerkoles?"),
    (NONE, "how many pieces per kiosk tomorrow?", "ilang piraso bawat kiosk bukas?",
     "pila ka piraso matag kiosk ugma?", "pila ka piraso kada kiosk buwas?",
     "pira nga piraso kada kiosk buwas?", "pirang piraso kada kiosk sa aga?"),
    (NONE, "plan for tomorrow please", "plano para bukas po", "plano para ugma palihug",
     "plano para buwas palihog", "plano para buwas alayon", "plano para sa aga tabi"),
    (NONE, "how much do we bake for the Mall kiosk tomorrow?",
     "ilan ang lulutuin para sa Mall kiosk bukas?", "pila ang lutuon para sa Mall kiosk ugma?",
     "pila ang lutuon para sa Mall kiosk buwas?", "pira an lulutuon para ha Mall kiosk buwas?",
     "pira an lulutoon para sa Mall kiosk sa aga?"),
    (NONE, "is tomorrow's plan ready?", "handa na ba ang plano bukas?",
     "andam na ba ang plano ugma?", "handa na bala ang plano buwas?",
     "andam na ba an plano buwas?", "lista na daw an plano sa aga?"),
    (NONE, "what's the production for Thursday?", "ano ang produksyon sa Huwebes?",
     "unsa ang produksyon sa Huwebes?", "ano ang produksyon naton sa Huwebes?",
     "ano an produksyon ha Huwebes?", "ano an produksyon sa Huwebes?"),
]  # fmt: skip

CONFIRM: list[Row] = [
    (NONE, "ok", "ok po", "ok na", "ok na ina", "ok na ini", "ok na tabi"),
    (NONE, "approved", "aprubado", "aprobado na", "aprobado na ina", "aprobado na ini",
     "aprobado na iyan"),
    (NONE, "go ahead with that plan", "sige, ituloy ang plano", "sige, padayon ang plano",
     "sige, ipadayon ang plano", "sige, padayuna an plano", "sige, ipadagos an plano"),
    (NONE, "confirmed", "kumpirmado", "kumpirmado na", "kumpirmado na ina", "kumpirmado na ini",
     "kumpirmado na iyan"),
    (NONE, "looks good, confirm it", "ayos, i-confirm mo na", "nindot, i-confirm na",
     "maayo, i-confirm na", "maupay, i-confirm na", "marhay, i-confirm na"),
    (NONE, "yes, that's fine", "oo, ayos lang", "oo, okay ra", "huo, okay lang", "oo, okay la",
     "iyo, okay lang"),
    (NONE, "all good, go", "go na po", "go na ta", "go na kita", "go na la", "go na tabi"),
    (NONE, "approve the plan", "aprubahan ang plano", "aprobahi ang plano",
     "aprobahan ang plano", "aprobahi an plano", "aprobaran an plano"),
    (NONE, "ok, bake that", "sige, lutuin na yan", "sige, lutoa na na", "sige, lutua na ina",
     "sige, lutua na iton", "sige, lutoon na iyan"),
    (NONE, "fine by me, confirm", "ayos sa akin, confirm", "okay ra nako, confirm",
     "okay lang sa akon, confirm", "okay la ha akon, confirm", "okay lang sa sako, confirm"),
]  # fmt: skip

# Mia's draft plan reply (replies.plan_text), the previous message of every confirm case: its
# head and lines from the reply keys of each language.
_DRAFTED = (("Classic", 3, 144), ("Special", 2, 72), ("Ube", 1, 36))


def _draft(lang: str) -> str:
    day = (TODAY + dt.timedelta(days=1)).isoformat()
    status = t("pp.plan.status.draft", lang)
    head = t("pp.plan.head", lang, date=day, status=status, minutes=120)
    lines = [t("pp.plan.line", lang, item=i, batches=b, pieces=p) for i, b, p in _DRAFTED]
    return "\n".join([head, *lines])


DRAFT: dict[str, str] = {lang: _draft(lang) for lang in GATED_LANGS}

ORDERS: list[Row] = [
    (NONE, "are the customer orders in tomorrow's plan?",
     "kasama ba sa plano bukas ang mga order?", "apil ba sa plano ugma ang mga order?",
     "upod bala sa plano buwas ang mga order?", "upod ba ha plano buwas an mga order?",
     "kaiba daw sa plano sa aga an mga order?"),
    (NONE, "how many pieces in the plan are for orders?",
     "ilang piraso sa plano ang para sa order?", "pila ka piraso sa plano ang para sa order?",
     "pila ka piraso sa plano ang para sa mga order?",
     "pira nga piraso ha plano an para ha order?", "pirang piraso sa plano an para sa order?"),
    (NONE, "does the plan count the Mall kiosk's pickup orders?",
     "kasama ba sa plano ang pickup orders ng Mall kiosk?",
     "apil ba sa plano ang pickup orders sa Mall kiosk?",
     "upod bala sa plano ang pickup orders sang Mall kiosk?",
     "upod ba ha plano an pickup orders han Mall kiosk?",
     "kaiba daw sa plano an pickup orders kan Mall kiosk?"),
    (NONE, "show the plan with the orders", "ipakita ang plano kasama ang mga order",
     "ipakita ang plano apil ang mga order", "ipakita ang plano upod ang mga order",
     "ipakita an plano upod an mga order", "ipahiling an plano kaiba an mga order"),
    (NONE, "tomorrow's plan with the orders please", "plano bukas kasama ang order po",
     "plano ugma apil ang order palihug", "plano buwas upod ang order palihog",
     "plano buwas upod an order alayon", "plano sa aga kaiba an order tabi"),
    (NONE, "is the order of 30 Classic in the plan?", "nasa plano ba ang order na 30 Classic?",
     "naa ba sa plano ang order nga 30 Classic?", "yara bala sa plano ang order nga 30 Classic?",
     "aadi ba ha plano an order nga 30 Classic?", "yaon daw sa plano an order na 30 Classic?"),
    (NONE, "how many orders are in tomorrow's plan?", "ilang order ang nasa plano bukas?",
     "pila ka order ang naa sa plano ugma?", "pila ka order ang yara sa plano buwas?",
     "pira nga order an aadi ha plano buwas?", "pirang order an yaon sa plano sa aga?"),
    (NONE, "did the confirmed orders go into the plan?",
     "napasok ba sa plano ang mga confirmed na order?",
     "nasulod ba sa plano ang mga confirmed nga order?",
     "nasulod bala sa plano ang mga confirmed nga order?",
     "nasulod ba ha plano an mga confirmed nga order?",
     "nakalaog daw sa plano an mga confirmed na order?"),
    (NONE, "the Street stall's plan line with its orders",
     "ang linya ng Street stall sa plano kasama ang order",
     "ang linya sa Street stall sa plano apil ang order",
     "ang linya sang Street stall sa plano upod ang order",
     "an linya han Street stall ha plano upod an order",
     "an linya kan Street stall sa plano kaiba an order"),
    (NONE, "how much of the plan is orders?", "gaano karami sa plano ang order?",
     "pila sa plano ang order?", "pila sa plano ang para sa order?",
     "pira ha plano an para ha order?", "gurano kadakol sa plano an order?"),
]  # fmt: skip

CHANGE: list[Row] = [
    (_ch("Ube", "add", 1), "add one batch of ube", "dagdagan ng isang batch ang ube",
     "dugangi og usa ka batch ang ube", "dugangan sang isa ka batch ang ube",
     "dugangi hin usa nga batch an ube", "dagdagan nin saro na batch an ube"),
    (_ch("Classic", "remove", 1), "one batch less of classic", "bawasan ng isang batch ang classic",
     "kuhai og usa ka batch ang classic", "buhini sang isa ka batch ang classic",
     "kuhai hin usa nga batch an classic", "bawasan nin saro na batch an classic"),
    (_ch("Special", "set", 3), "make special 3 batches", "gawin 3 batch ang special",
     "himoa 3 ka batch ang special", "himua 3 ka batch ang special",
     "himua 3 nga batch an special", "gibohon 3 na batch an special"),
    (_ch("Classic", "add", 2), "add 2 batches of classic", "dagdag 2 batch sa classic",
     "dugang 2 ka batch sa classic", "dugang pa 2 ka batch sa classic",
     "dugang 2 nga batch ha classic", "dagdag 2 na batch sa classic"),
    (_ch("Salted egg", "remove", 1), "remove 1 batch of salted egg",
     "bawas 1 batch sa salted egg", "kuhai 1 ka batch ang salted egg",
     "buhini 1 ka batch ang salted egg", "kuhai 1 nga batch an salted egg",
     "bawasi 1 na batch an salted egg"),
    (_ch("Puto bumbong", "set", 2), "set puto bumbong to 2 batches",
     "gawing 2 batch ang puto bumbong", "himoa nga 2 ka batch ang puto bumbong",
     "himua nga 2 ka batch ang puto bumbong", "himua nga 2 nga batch an puto bumbong",
     "gibohon na 2 na batch an puto bumbong"),
    (_ch("Cheese overload", "add", 1), "plus 1 batch cheese overload",
     "plus 1 batch sa cheese overload", "dugang 1 ka batch sa cheese overload",
     "dugangi 1 ka batch ang cheese overload", "dugangi 1 nga batch an cheese overload",
     "dagdagi 1 na batch an cheese overload"),
    (_ch("Ube", "remove", 2), "less 2 batches of ube", "bawasan ng 2 batch ang ube",
     "kuhai og 2 ka batch ang ube", "buhini sang 2 ka batch ang ube",
     "kuhai hin 2 nga batch an ube", "bawasan nin 2 na batch an ube"),
    (_ch("Classic", "set", 4), "classic 4 batches only", "4 batch lang ang classic",
     "4 ka batch ra ang classic", "4 ka batch lang ang classic", "4 nga batch la an classic",
     "4 na batch sana an classic"),
    (_ch("Special", "add", 1), "one more batch of special tomorrow",
     "isa pang batch ng special bukas", "usa pa ka batch sa special ugma",
     "isa pa ka batch sang special buwas", "usa pa nga batch han special buwas",
     "saro pang batch nin special sa aga"),
]  # fmt: skip

BATCH_SHEET: list[Row] = [
    (_i("Classic"), "batch sheet classic", "batch sheet ng classic", "batch sheet sa classic",
     "batch sheet sang classic", "batch sheet han classic", "batch sheet kan classic"),
    (_i("Ube"), "how many eggs do I need for the ube?", "ilang itlog ang kailangan sa ube?",
     "pila ka itlog ang kinahanglan sa ube?", "pila ka itlog ang kinahanglan para sa ube?",
     "pira nga itlog an kinahanglan ha ube?", "pirang itlog an kaipuhan sa ube?"),
    (_i("Special"), "ingredients for tomorrow's special", "mga sangkap para sa special bukas",
     "mga sagol para sa special ugma", "mga sangkap para sa special buwas",
     "mga sangkap para ha special buwas", "mga sangkap para sa special sa aga"),
    (_i("Salted egg"), "what does a batch of salted egg cost?",
     "magkano ang isang batch ng salted egg?", "pila ang gasto sa usa ka batch sa salted egg?",
     "pila ang gasto sang isa ka batch sang salted egg?",
     "pira an gasto han usa nga batch han salted egg?",
     "magkano an gastos kan saro na batch nin salted egg?"),
    (_i("Cheese overload"), "sheet for cheese overload", "sheet ng cheese overload",
     "sheet sa cheese overload", "sheet sang cheese overload", "sheet han cheese overload",
     "sheet kan cheese overload"),
    (_i("Classic"), "how much rice flour for the classic tomorrow?",
     "ilang kilo ng galapong para sa classic bukas?",
     "pila ka kilo nga galapong para sa classic ugma?",
     "pila ka kilo nga galapong para sa classic buwas?",
     "pira nga kilo nga galapong para ha classic buwas?",
     "pirang kilo na galapong para sa classic sa aga?"),
    (_i("Puto bumbong"), "cost per piece of puto bumbong",
     "magkano bawat piraso ng puto bumbong", "pila matag piraso sa puto bumbong",
     "pila kada piraso sang puto bumbong", "pira kada piraso han puto bumbong",
     "magkano kada piraso kan puto bumbong"),
    (_i("Ube"), "batch sheet ube please", "batch sheet ube po", "batch sheet ube palihug",
     "batch sheet ube palihog", "batch sheet ube alayon", "batch sheet ube tabi"),
    (_i("Special"), "what goes into a batch of special?",
     "ano ang laman ng isang batch ng special?", "unsa ang sulod sa usa ka batch sa special?",
     "ano ang sulod sang isa ka batch sang special?",
     "ano an sulod han usa nga batch han special?", "ano an laog kan saro na batch nin special?"),
    (_i("Classic"), "coconuts needed for the classic batches",
     "ilang niyog ang kailangan sa classic", "pila ka lubi ang kinahanglan sa classic",
     "pila ka lubi ang kinahanglan sa mga classic", "pira nga lubi an kinahanglan ha classic",
     "pirang niyog an kaipuhan sa classic"),
]  # fmt: skip

RECIPE: list[Row] = [
    (_i("Classic"), "recipe classic: 48 pieces, 2 kg rice flour, 1 tray eggs, 6 coco, 45 min",
     "recipe ng classic: 48 piraso, 2 kg rice flour, 1 tray itlog, 6 niyog, 45 min",
     "resipe sa classic: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 45 minutos",
     "resipe sang classic: 48 piraso, 2 kilo rf, 1 tray itlog, 6 niyog, 45 min",
     "resipe han classic: 48 piraso, 2 kg flour, 1 tray itlog, 6 niyog, 45 min",
     "resipe kan classic: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 45 minuto"),
    (_i("Ube"), "ube recipe: 36 pcs, 2 kg flour, 1 tray egg, 6 coco, 1 kg sugar, 50 min",
     "recipe ng ube: 36 piraso, 2 kg flour, 1 tray itlog, 6 niyog, 1 kg asukal, 50 min",
     "resipe sa ube: 36 piraso, 2 kg flour, 1 tray itlog, 6 niyog, 1 kg asukal, 50 minutos",
     "resipe sang ube: 36 piraso, 2 kg flour, 1 tray itlog, 6 niyog, 1 kg asukal, 50 min",
     "resipe han ube: 36 piraso, 2 kg flour, 1 tray itlog, 6 niyog, 1 kg asukal, 50 minuto",
     "resipe kan ube: 36 piraso, 2 kg flour, 1 tray itlog, 6 niyog, 1 kg asukal, 50 min"),
    (_i("Special"), ("special: 36 pieces per batch, 2 kg rf, 1 tray eggs, 1 kg sugar, 1 pack bl,"
      " 45 min"),
     "special: 36 piraso kada batch, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon, 45 min",
     "special: 36 piraso matag batch, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon, 45 min",
     "special: 36 piraso kada batch, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon, 45 minuto",
     "special: 36 piraso kada batch, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon, 45 minutos",
     "special: 36 piraso kada batch, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack bl, 45 min"),
    (_i("Salted egg"), "recipe salted egg: 36 pcs, 2 kg rf, 1 tray egg, 12 maalat, 45 min",
     "recipe ng salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 12 maalat, 45 min",
     "resipe sa salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 12 maalat, 45 min",
     "resipe sang salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 12 pula, 45 min",
     "resipe han salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 12 pula, 45 min",
     "resipe kan salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 12 maalat, 45 minuto"),
    (_i("Cheese overload"), ("set the cheese overload recipe: 36 pcs, 2 kg flour, 500 g cheese,"
      " 1 tray eggs, 45 min"),
     ("ilagay ang recipe ng cheese overload: 36 piraso, 2 kg flour, 500 g keso, 1 tray itlog,"
      " 45 min"),
     ("ibutang ang resipe sa cheese overload: 36 piraso, 2 kg flour, 500 g keso, 1 tray itlog,"
      " 45 min"),
     ("ibutang ang resipe sang cheese overload: 36 piraso, 2 kg flour, 500 g keso, 1 tray"
      " itlog, 45 min"),
     ("ibutang an resipe han cheese overload: 36 piraso, 2 kg flour, 500 g keso, 1 tray itlog,"
      " 45 min"),
     ("ibutang an resipe kan cheese overload: 36 piraso, 2 kg flour, 500 g keso, 1 tray itlog,"
      " 45 min")),
    (_i("Puto bumbong"), "puto bumbong recipe: 48 pcs, 3 kg rf, 1 kg sugar, 1 pack bl, 30 min",
     "recipe ng puto bumbong: 48 piraso, 3 kg rf, 1 kg asukal, 1 pack dahon, 30 min",
     "resipe sa puto bumbong: 48 piraso, 3 kg rf, 1 kg asukal, 1 pack dahon, 30 min",
     "resipe sang puto bumbong: 48 piraso, 3 kg rf, 1 kg asukal, 1 pack dahon, 30 minuto",
     "resipe han puto bumbong: 48 piraso, 3 kg rf, 1 kg asukal, 1 pack dahon, 30 minutos",
     "resipe kan puto bumbong: 48 piraso, 3 kg rf, 1 kg asukal, 1 pack dahon, 30 min"),
    (_i("Classic"), "change the classic recipe: 50 pieces, 2.5 kg rf, 1 tray egg, 6 coco, 45 min",
     "palitan ang recipe ng classic: 50 piraso, 2.5 kg rf, 1 tray itlog, 6 niyog, 45 min",
     "usba ang resipe sa classic: 50 piraso, 2.5 kg rf, 1 tray itlog, 6 niyog, 45 min",
     "ilisan ang resipe sang classic: 50 piraso, 2.5 kg rf, 1 tray itlog, 6 niyog, 45 min",
     "igbag-o an resipe han classic: 50 piraso, 2.5 kg rf, 1 tray itlog, 6 niyog, 45 min",
     "ribaying an resipe kan classic: 50 piraso, 2.5 kg rf, 1 tray itlog, 6 niyog, 45 min"),
    (_i("Ube"), "new ube recipe: 40 pcs, 2 kg rf, 1 tray egg, 1 kg sugar, 1 pack bl, 45 min",
     "bagong recipe ng ube: 40 piraso, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon, 45 min",
     "bag-ong resipe sa ube: 40 piraso, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon, 45 min",
     ("bag-o nga resipe sang ube: 40 piraso, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 45 min"),
     ("bag-o nga resipe han ube: 40 piraso, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 45 min"),
     ("bagong resipe kan ube: 40 piraso, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 45 min")),
    (_i("Special"), "recipe for special: 36 pcs, 2 kg rice flour, 2 tray eggs, 1 kg sugar, 40 min",
     "recipe para sa special: 36 piraso, 2 kg rice flour, 2 tray itlog, 1 kg asukal, 40 min",
     "resipe para sa special: 36 piraso, 2 kg rice flour, 2 tray itlog, 1 kg asukal, 40 min",
     "resipe para sa special: 36 piraso, 2 kilo rice flour, 2 tray itlog, 1 kg asukal, 40 min",
     "resipe para ha special: 36 piraso, 2 kg rice flour, 2 tray itlog, 1 kg asukal, 40 min",
     "resipe para sa special: 36 piraso, 2 kg rice flour, 2 tray itlog, 1 kg asukal, 40 minuto"),
    (_i("Classic"), "classic recipe: 48 pcs, 2 kg rf, 1 tray egg, 6 coconut, 1 pack bl, 45 mins",
     "recipe classic: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 1 pack dahon, 45 minutos",
     "resipe classic: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 1 pack dahon, 45 min",
     "resipe classic: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 1 pack dahon, 45 minutos",
     "resipe classic: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 1 pack dahon, 45 minuto",
     "resipe classic: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 1 pack bl, 45 min"),
]  # fmt: skip

BATCH: list[Row] = [
    (_i("Classic"), "batch 2 classic 45 ok 3 burnt", "batch 2 classic 45 ok 3 sunog",
     "batch 2 sa classic 45 ok 3 sunog", "batch 2 sang classic 45 ok 3 sunog",
     "batch 2 han classic 45 ok 3 sunog", "batch 2 kan classic 45 ok 3 sunog"),
    (_i("Ube"), "ube batch 1: 34 good, 2 dropped", "ube batch 1: 34 ok, 2 nahulog",
     "ube batch 1: 34 maayos, 2 nahulog", "ube batch 1: 34 ok, 2 nahulog sa salog",
     "ube batch 1: 34 ok, 2 nahulog ha salog", "ube batch 1: 34 ok, 2 nahulog sa daga"),
    (_i("Special"), "batch 3 special 36 ok", "batch 3 special 36 piraso ok",
     "batch 3 sa special 36 ok", "batch 3 sang special 36 ok", "batch 3 han special 36 ok",
     "batch 3 kan special 36 ok"),
    (_i("Salted egg"), "batch 1 salted egg 30 ok 6 undercooked",
     "batch 1 salted egg 30 ok 6 hilaw", "batch 1 sa salted egg 30 ok 6 hilaw",
     "batch 1 sang salted egg 30 ok 6 hilaw", "batch 1 han salted egg 30 ok 6 hilaw",
     "batch 1 kan salted egg 30 ok 6 hilaw"),
    (_i("Cheese overload"), "cheese overload batch 2, 35 good, 1 other",
     "cheese overload batch 2, 35 ok, 1 iba", "cheese overload batch 2, 35 maayos, 1 iba",
     "cheese overload batch 2, 35 maayos, 1 iba pa", "cheese overload batch 2, 35 ok, 1 iba la",
     "cheese overload batch 2, 35 ok, 1 iba tabi"),
    (_i("Classic"), "batch #4 classic 48 ok", "batch #4 classic 48 ok lahat",
     "batch #4 classic 48 ok tanan", "batch #4 classic 48 ok tanan subong",
     "batch #4 classic 48 ok ngatanan", "batch #4 classic 48 ok gabos"),
    (_i("Puto bumbong"), "batch 1 puto bumbong 44 ok 4 burnt",
     "batch 1 puto bumbong 44 ok 4 sunog", "batch 1 sa puto bumbong 44 ok 4 sunog",
     "batch 1 sang puto bumbong 44 ok 4 sunog", "batch 1 han puto bumbong 44 ok 4 sunog",
     "batch 1 kan puto bumbong 44 ok 4 sunog"),
    (_i("Classic"), "batch 3 classic: 46 ok, 2 dropped", "batch 3 classic: 46 ok, 2 nahulog",
     "batch 3 classic: 46 maayos, 2 nahulog", "batch 3 classic: 46 ok, 2 ang nahulog",
     "batch 3 classic: 46 ok, 2 an nahulog", "batch 3 classic: 46 ok, 2 an nahulog tabi"),
    (_i("Ube"), "batch 2 ube 33 ok 3 undercooked", "batch 2 ube 33 ok 3 hilaw",
     "batch 2 sa ube 33 ok 3 hilaw", "batch 2 sang ube 33 ok 3 hilaw",
     "batch 2 han ube 33 ok 3 hilaw", "batch 2 kan ube 33 ok 3 hilaw"),
    (_i("Special"), "batch 1 special 35 good 1 burnt", "batch 1 special 35 maayos 1 sunog",
     "batch 1 sa special 35 maayos 1 sunog", "batch 1 sang special 35 maayos 1 sunog",
     "batch 1 han special 35 maayos 1 sunog", "batch 1 kan special 35 maayos 1 sunog"),
]  # fmt: skip

DISPATCH: list[Row] = [
    (NONE, "what's arriving tomorrow?", "ano ang darating bukas?", "unsa ang moabot ugma?",
     "ano ang maabot buwas?", "ano an maabot buwas?", "ano an maabot sa aga?"),
    (NONE, "dispatch list for the mall", "dispatch list para sa mall",
     "dispatch list para sa mall palihug", "dispatch list para sa mall palihog",
     "dispatch list para ha mall", "dispatch list para sa mall tabi"),
    (NONE, "how many classic are coming to our kiosk?",
     "ilang classic ang darating sa kiosk namin?", "pila ka classic ang moabot sa among kiosk?",
     "pila ka classic ang maabot sa amon kiosk?", "pira nga classic an maabot ha amon kiosk?",
     "pirang classic an maabot sa samong kiosk?"),
    (NONE, "what's coming in today?", "ano ang darating ngayon?", "unsa ang moabot karon?",
     "ano ang maabot subong?", "ano an maabot yana?", "ano an maabot ngunyan?"),
    (NONE, "when does the delivery from the commissary come?",
     "kailan darating ang delivery galing commissary?",
     "kanus-a moabot ang delivery gikan sa commissary?",
     "san-o maabot ang delivery halin sa commissary?",
     "san-o maabot an delivery tikang ha commissary?",
     "noarin maabot an delivery hali sa commissary?"),
    (NONE, "what will the driver bring us?", "ano ang dadalhin ng driver sa amin?",
     "unsa ang dad-on sa driver para namo?", "ano ang dalhon sang driver para sa amon?",
     "ano an dadad-on han driver para ha amon?", "ano an darahon kan driver para samo?"),
    (NONE, "send me our dispatch list", "ipadala ang dispatch list namin",
     "ipadala ang among dispatch list", "ipadala ang amon dispatch list",
     "ipadara an amon dispatch list", "ipadara an samong dispatch list"),
    (NONE, "how many pieces are we getting tomorrow?", "ilang piraso ang matatanggap namin bukas?",
     "pila ka piraso among madawat ugma?", "pila ka piraso ang mabaton namon buwas?",
     "pira nga piraso an amon mababaton buwas?", "pirang piraso an maaako mi sa aga?"),
    (NONE, "what's on the delivery for the Mall kiosk?",
     "ano ang laman ng delivery para sa Mall kiosk?",
     "unsa ang sulod sa delivery para sa Mall kiosk?",
     "ano ang sulod sang delivery para sa Mall kiosk?",
     "ano an sulod han delivery para ha Mall kiosk?",
     "ano an laog kan delivery para sa Mall kiosk?"),
    (NONE, "is our bibingka on its way?", "papunta na ba ang bibingka namin?",
     "padulong na ba ang among bibingka?", "padulong na bala ang amon bibingka?",
     "papakadto na ba an amon bibingka?", "pasiring na daw an samong bibingka?"),
]  # fmt: skip

MALL, STALL = {"kiosk": "Mall kiosk"}, {"kiosk": "Street stall"}
DELIVERED: list[Row] = [
    (MALL, "delivered to the mall", "delivered na sa mall", "na-deliver na sa mall",
     "na-deliver na sa mall kiosk", "na-deliver na ha mall", "na-deliver na sa mall tabi"),
    (STALL, "dropped off at the street stall", "naihatid na sa street stall",
     "nahatod na sa street stall", "naihatod na sa street stall", "naihatod na ha street stall",
     "naitao na sa street stall"),
    (MALL, "Mall kiosk done, all delivered", "tapos na sa Mall kiosk, naihatid lahat",
     "human na sa Mall kiosk, nahatod tanan", "tapos na sa Mall kiosk, naihatod tanan",
     "human na ha Mall kiosk, naihatod ngatanan", "tapos na sa Mall kiosk, naitao gabos"),
    (STALL, "delivery done at the stall", "tapos na ang delivery sa stall",
     "human na ang delivery sa stall", "tapos na ang delivery sa stall subong",
     "human na an delivery ha stall", "tapos na an delivery sa stall"),
    (MALL, "just delivered at the Mall kiosk", "kaka-deliver ko lang sa Mall kiosk",
     "bag-o lang ko nag-deliver sa Mall kiosk", "bag-o lang ako nag-deliver sa Mall kiosk",
     "bag-o la ako nag-deliver ha Mall kiosk", "bago pa sana ako nag-deliver sa Mall kiosk"),
    (STALL, "delivered, street stall", "delivered na, street stall", "nahatod na, street stall",
     "naihatod na, street stall", "naihatod na, street stall la", "naitao na, street stall"),
    (MALL, "mall kiosk: delivered", "mall kiosk: naihatid na", "mall kiosk: nahatod na",
     "mall kiosk: naihatod na", "mall kiosk: naihatod na la", "mall kiosk: naitao na"),
    (STALL, "finished the stall delivery", "natapos ko na ang delivery sa stall",
     "nahuman nako ang delivery sa stall", "natapos ko na ang delivery sa stall",
     "nahuman ko na an delivery ha stall", "natapos ko na an delivery sa stall"),
    (MALL, "the mall kiosk has its bibingka now", "nasa mall kiosk na ang bibingka nila",
     "naa na sa mall kiosk ang ilang bibingka", "yara na sa mall kiosk ang ila bibingka",
     "aadi na ha mall kiosk an ira bibingka", "yaon na sa mall kiosk an saindang bibingka"),
    (STALL, "handed the trays over at the street stall", "naibigay ko na ang tray sa street stall",
     "nahatag na nako ang tray sa street stall", "nahatag ko na ang tray sa street stall",
     "naihatag ko na an tray ha street stall", "naitao ko na an tray sa street stall"),
]  # fmt: skip

CAPACITY: list[Row] = [
    (_i("Classic", number=200), "can we do 200 classic on Dec 24?",
     "kaya ba ang 200 classic sa Dec 24", "makaya ba ang 200 classic sa Dec 24?",
     "masarangan bala ang 200 classic sa Dec 24?", "kaya ba an 200 classic ha Dec 24?",
     "kaya daw an 200 classic sa Dec 24?"),
    (_i("Ube", number=100), "is there oven room for 100 ube on Saturday?",
     "may lugar pa ba sa oven para sa 100 ube sa Sabado?",
     "naa pa bay luna sa oven para sa 100 ube sa Sabado?",
     "may lugar pa bala sa oven para sa 100 ube sa Sabado?",
     "may-ada pa ba lugar ha oven para ha 100 ube ha Sabado?",
     "igwa pa daw lugar sa oven para sa 100 ube sa Sabado?"),
    (_i("Special", number=150), "can the ovens bake 150 special tomorrow?",
     "kaya ba ng oven ang 150 special bukas?", "kaya ba sa oven ang 150 special ugma?",
     "kaya bala sang oven ang 150 special buwas?", "kaya ba han oven an 150 special buwas?",
     "kaya daw kan oven an 150 special sa aga?"),
    (_i("Classic", number=300), "300 classic on Dec 23, possible?",
     "300 classic sa Dec 23, kaya ba?", "300 classic sa Dec 23, makaya ba?",
     "300 classic sa Dec 23, masarangan bala?", "300 classic ha Dec 23, kaya ba?",
     "300 classic sa Dec 23, kaya daw?"),
    (_i("Salted egg", number=72), "do we have room for 72 salted egg on Friday?",
     "may puwang pa ba para sa 72 salted egg sa Biyernes?",
     "naa pa bay luna para sa 72 salted egg sa Biyernes?",
     "may lugar pa bala para sa 72 salted egg sa Biyernes?",
     "may-ada pa ba lugar para ha 72 salted egg ha Biyernes?",
     "igwa pa daw lugar para sa 72 salted egg sa Biyernes?"),
    (_i("Puto bumbong", number=96), "can the oven handle 96 puto bumbong on Dec 31?",
     "kaya ba ng oven ang 96 puto bumbong sa Dec 31?",
     "kaya ba sa oven ang 96 puto bumbong sa Dec 31?",
     "kaya bala sang oven ang 96 puto bumbong sa Dec 31?",
     "kaya ba han oven an 96 puto bumbong ha Dec 31?",
     "kaya daw kan oven an 96 puto bumbong sa Dec 31?"),
    (_i("Classic", number=240), "can we fit 240 classic on Nov 30?",
     "kasya pa ba ang 240 classic sa Nov 30?", "masulod pa ba ang 240 classic sa Nov 30?",
     "masulod pa bala ang 240 classic sa Nov 30?", "masulod pa ba an 240 classic ha Nov 30?",
     "makakalaog pa daw an 240 classic sa Nov 30?"),
    (_i("Cheese overload", number=60), "is 60 cheese overload doable on Sunday?",
     "kaya ba ang 60 cheese overload sa Linggo?", "makaya ba ang 60 cheese overload sa Dominggo?",
     "masarangan bala ang 60 cheese overload sa Domingo?",
     "kaya ba an 60 cheese overload ha Domingo?", "kaya daw an 60 cheese overload sa Domingo?"),
    (_i("Ube", number=180), "can we make 180 ube for Dec 22?",
     "kaya ba nating gumawa ng 180 ube para sa Dec 22?",
     "makahimo ba ta og 180 ube para sa Dec 22?",
     "makahimo bala kita sang 180 ube para sa Dec 22?",
     "makakahimo ba kita hin 180 ube para ha Dec 22?",
     "makakagibo daw kita nin 180 ube para sa Dec 22?"),
    (_i("Special", number=120), "oven capacity for 120 special on Saturday?",
     "kapasidad ng oven para sa 120 special sa Sabado?",
     "kapasidad sa oven para sa 120 special sa Sabado?",
     "kapasidad sang oven para sa 120 special sa Sabado?",
     "kapasidad han oven para ha 120 special ha Sabado?",
     "kapasidad kan oven para sa 120 special sa Sabado?"),
]  # fmt: skip

# The fresh rows for the D40 rerun (never scored before); halves by seed parity, as the spent.
F_PLAN: list[Row] = [
    (NONE, "what's the bake list for tomorrow?", "ano ang listahan ng lulutuin bukas?",
     "unsa ang listahan sa lutuon ugma?", "ano ang listahan sang lutuon buwas?",
     "ano an listahan han lulutuon buwas?", "ano an lista kan lulutoon sa aga?"),
    (NONE, "Mia, the production plan for tomorrow please",
     "Mia, pakibigay ang production plan bukas", "Mia, palihug ihatag ang production plan ugma",
     "Mia, palihog ihatag ang production plan buwas",
     "Mia, alayon ihatag an production plan buwas", "Mia, tabi itao an production plan sa aga"),
    (NONE, "how many batches are we baking on Wednesday?",
     "ilang batch ang lulutuin natin sa Miyerkules?", "pila ka batch atong lutuon sa Miyerkules?",
     "pila ka batch ang lutuon naton sa Miyerkoles?",
     "pira nga batch an aton lulutuon ha Miyerkoles?", "pirang batch an lulutoon ta sa Miyerkoles?"),
    (NONE, "give me the plan for tomorrow, per item", "ibigay mo ang plano bukas, bawat item",
     "ihatag ang plano ugma, matag item", "ihatag ang plano buwas, kada item",
     "ihatag an plano buwas, kada item", "itao an plano sa aga, kada item"),
    (NONE, "what does the commissary bake tomorrow?", "ano ang lulutuin ng commissary bukas?",
     "unsa ang lutuon sa commissary ugma?", "ano ang lutuon sang commissary buwas?",
     "ano an lulutuon han commissary buwas?", "ano an lulutoon kan commissary sa aga?"),
    (NONE, "what's the plan for Friday?", "ano ang plano sa Biyernes?",
     "unsa ang plano sa Biyernes?", "ano bala ang plano sa Biyernes?", "ano an plano ha Biyernes?",
     "ano daw an plano sa Biyernes?"),
    (NONE, "how many pieces go to the Street stall in tomorrow's plan?",
     "ilang piraso ang para sa Street stall sa plano bukas?",
     "pila ka piraso ang para sa Street stall sa plano ugma?",
     "pila ka piraso ang para sa Street stall sa plano buwas?",
     "pira nga piraso an para ha Street stall ha plano buwas?",
     "pirang piraso an para sa Street stall sa plano sa aga?"),
    (NONE, "Nonoy here, what do we bake tomorrow and how much?",
     "si Nonoy ito, ano at ilan ang lulutuin bukas?", "si Nonoy ni, unsa ug pila ang lutuon ugma?",
     "si Nonoy ini, ano kag pila ang lutuon buwas?",
     "hi Nonoy ini, ano ngan pira an lulutuon buwas?",
     "si Nonoy ini, ano asin pira an lulutoon sa aga?"),
    (NONE, "tomorrow's baking schedule?", "iskedyul ng luto bukas?", "iskedyul sa pagluto ugma?",
     "iskedyul sang pagluto buwas?", "iskedyul han pagluto buwas?", "iskedyul kan pagluto sa aga?"),
    (NONE, "what are the batch counts in the draft plan?", "ilan ang batch sa draft na plano?",
     "pila ang batch sa draft nga plano?", "pila bala ang batch sa draft nga plano?",
     "pira an batch ha draft nga plano?", "pira an batch sa draft na plano?"),
]  # fmt: skip

F_CONFIRM: list[Row] = [
    (NONE, "ok, lock it in", "sige, i-lock na", "sige, i-lock na na", "sige, i-lock na ina",
     "sige, i-lock na ito", "sige, i-lock na iyan"),
    (NONE, "yes confirm", "oo, i-confirm", "oo, i-confirm na", "huo, i-confirm",
     "oo, i-confirm iton", "iyo, i-confirm"),
    (NONE, "that plan is good, go ahead", "maayos ang planong iyan, tuloy",
     "maayo na nga plano, padayon", "maayo ina nga plano, sige padayon",
     "maupay ito nga plano, padayon", "marhay an planong iyan, padagos"),
    (NONE, "approve it", "aprubahan mo na", "aprobahi na", "aprobahan mo na", "aprobahi na la",
     "aprobaran na"),
    (NONE, "sure, we'll bake that", "sige, iyan ang lulutuin namin", "sige, mao na among lutuon",
     "sige, amo na ang lutuon namon", "sige, amo iton an amon lulutuon",
     "sige, iyan an lulutoon mi"),
    (NONE, "confirm the draft", "i-confirm ang draft", "i-confirm ang draft palihug",
     "i-confirm ang draft palihog", "i-confirm an draft alayon", "i-confirm an draft tabi"),
    (NONE, "good as is, confirm", "ayos na yan, confirm", "okay na na, confirm",
     "okay na ina, confirm", "okay na iton, confirm", "okay na iyan, confirm"),
    (NONE, "go with the draft", "ituloy ang draft", "padayon sa draft", "padayuna ang draft",
     "ipadayon an draft", "ipadagos an draft"),
    (NONE, "noted, approve", "noted, aprubado na", "noted, aprobado na ni",
     "noted, aprobado na dya", "noted, aprobado na ito", "noted, aprobado na ini"),
    (NONE, "yes Mia, that's the plan", "oo Mia, iyan na ang plano", "oo Mia, mao na ang plano",
     "huo Mia, amo na ina ang plano", "oo Mia, amo na iton an plano", "iyo Mia, iyan na an plano"),
]  # fmt: skip

F_ORDERS: list[Row] = [
    (NONE, "does tomorrow's plan include the pre-orders?",
     "kasama na ba ang mga pre-order sa plano bukas?",
     "apil na ba ang mga pre-order sa plano ugma?",
     "upod na bala ang mga pre-order sa plano buwas?",
     "upod na ba an mga pre-order ha plano buwas?",
     "kaiba na daw an mga pre-order sa plano sa aga?"),
    (NONE, "show tomorrow's plan with the order pieces",
     "ipakita ang plano bukas kasama ang piraso ng order",
     "ipakita ang plano ugma apil ang piraso sa order",
     "ipakita ang plano buwas upod ang piraso sang order",
     "ipakita an plano buwas upod an piraso han order",
     "ipahiling an plano sa aga kaiba an piraso kan order"),
    (NONE, "how many order pieces are in the Mall kiosk line of the plan?",
     "ilang piraso ng order ang nasa linya ng Mall kiosk sa plano?",
     "pila ka piraso sa order ang naa sa linya sa Mall kiosk sa plano?",
     "pila ka piraso sang order ang yara sa linya sang Mall kiosk sa plano?",
     "pira nga piraso han order an aadi ha linya han Mall kiosk ha plano?",
     "pirang piraso kan order an yaon sa linya kan Mall kiosk sa plano?"),
    (NONE, "plan for tomorrow, orders included", "plano bukas, kasama ang mga order",
     "plano ugma, apil ang mga order", "plano buwas, upod ang mga order",
     "plano buwas, upod an mga order", "plano sa aga, kaiba an mga order"),
    (NONE, "is the 24-piece order counted in the plan?",
     "bilang na ba sa plano ang order na 24 piraso?",
     "naihap na ba sa plano ang order nga 24 ka piraso?",
     "naisip na bala sa plano ang order nga 24 ka piraso?",
     "naihap na ba ha plano an order nga 24 ka piraso?",
     "bilang na daw sa plano an order na 24 piraso?"),
    (NONE, "what part of tomorrow's batches is for orders?",
     "aling bahagi ng batch bukas ang para sa order?",
     "unsang bahin sa batch ugma ang para sa order?",
     "diin nga bahin sang batch buwas ang para sa order?",
     "hain nga bahin han batch buwas an para ha order?",
     "arin na parte kan batch sa aga an para sa order?"),
    (NONE, "plan with the confirmed orders, please",
     "plano kasama ang kumpirmadong order, pakiusap",
     "plano apil ang kumpirmado nga order, palihug",
     "plano upod ang kumpirmado nga order, palihog",
     "plano upod an kumpirmado nga order, alayon", "plano kaiba an kumpirmadong order, tabi"),
    (NONE, "are the Street stall orders in tomorrow's batches?",
     "kasama ba ang order ng Street stall sa batch bukas?",
     "apil ba ang order sa Street stall sa batch ugma?",
     "upod bala ang order sang Street stall sa batch buwas?",
     "upod ba an order han Street stall ha batch buwas?",
     "kaiba daw an order kan Street stall sa batch sa aga?"),
    (NONE, "the plan, with orders and forecast", "ang plano, may order at forecast",
     "ang plano, naay order ug forecast", "ang plano, may order kag forecast",
     "an plano, may order ngan forecast", "an plano, may order asin forecast"),
    (NONE, "how many orders did the plan pick up for Wednesday?",
     "ilang order ang nakuha ng plano para sa Miyerkules?",
     "pila ka order ang nakuha sa plano para sa Miyerkules?",
     "pila ka order ang nakuha sang plano para sa Miyerkoles?",
     "pira nga order an nakuha han plano para ha Miyerkoles?",
     "pirang order an nakua kan plano para sa Miyerkoles?"),
]  # fmt: skip

# Each change names one item, a batch word, one number and (more or fewer) an add or remove
# word of the language; a set holds neither kind of word.
F_CHANGE: list[Row] = [
    (_ch("Ube", "add", 2), "put 2 more batches of ube", "dagdagan pa ng 2 batch ang ube",
     "idugang 2 ka batch sa ube", "dugangan 2 ka batch ang ube", "idugang 2 nga batch ha ube",
     "dagdagi nin 2 na batch an ube"),
    (_ch("Classic", "remove", 2), "reduce classic by 2 batches", "bawasan ang classic ng 2 batch",
     "kunhori og 2 ka batch ang classic", "buhinan sang 2 ka batch ang classic",
     "bawasi hin 2 nga batch an classic", "bawasi nin 2 na batch an classic"),
    (_ch("Special", "set", 4), "special should be 4 batches", "4 na batch dapat ang special",
     "4 ka batch dapat ang special", "dapat 4 ka batch ang special",
     "dapat 4 nga batch an special", "dapat 4 na batch an special"),
    (_ch("Salted egg", "add", 1), "add one batch to salted egg",
     "dagdag isang batch sa salted egg", "dugangi og usa ka batch ang salted egg",
     "dugangi sang isa ka batch ang salted egg", "dugangi hin usa nga batch an salted egg",
     "dagdagan nin saro na batch an salted egg"),
    (_ch("Cheese overload", "remove", 1), "minus 1 batch on cheese overload",
     "bawas ng 1 batch ang cheese overload", "kuhaan og 1 ka batch ang cheese overload",
     "buhin 1 ka batch sa cheese overload", "kuhaan hin 1 nga batch an cheese overload",
     "halion an 1 na batch kan cheese overload"),
    (_ch("Puto bumbong", "set", 3), "change puto bumbong to 3 batches",
     "palitan sa 3 batch ang puto bumbong", "ilisi og 3 ka batch ang puto bumbong",
     "ilisan sang 3 ka batch ang puto bumbong", "igbag-o ngadto ha 3 nga batch an puto bumbong",
     "ribayan nin 3 na batch an puto bumbong"),
    (_ch("Classic", "add", 1), "one extra batch of classic for tomorrow",
     "isang extra na batch ng classic para bukas", "usa ka extra nga batch sa classic para ugma",
     "isa ka extra nga batch sang classic para buwas",
     "usa nga extra nga batch han classic para buwas",
     "saro na extra na batch kan classic para sa aga"),
    (_ch("Ube", "remove", 1), "ube, 1 batch less", "ube, bawas 1 batch", "ube, kuhai 1 ka batch",
     "ube, buhini 1 ka batch", "ube, kuhai 1 nga batch", "ube, bawasi 1 na batch"),
    (_ch("Special", "set", 2), "set special at exactly 2 batches", "eksaktong 2 batch ang special",
     "eksakto 2 ka batch ang special", "eksakto nga 2 ka batch ang special",
     "eksakto nga 2 nga batch an special", "eksaktong 2 na batch an special"),
    (_ch("Cheese overload", "add", 2), "increase cheese overload by 2 batches",
     "dagdagan ng 2 batch ang cheese overload", "dugangi og 2 ka batch ang cheese overload",
     "dugangi sang 2 ka batch ang cheese overload", "dugangi hin 2 nga batch an cheese overload",
     "dugangan nin 2 na batch an cheese overload"),
]  # fmt: skip

F_BATCH_SHEET: list[Row] = [
    (_i("Classic"), "what do I need for the classic batches tomorrow?",
     "ano ang kailangan ko sa batch ng classic bukas?",
     "unsa ang akong kinahanglan sa batch sa classic ugma?",
     "ano ang kinahanglan ko sa batch sang classic buwas?",
     "ano an kinahanglan ko ha batch han classic buwas?",
     "ano an kaipuhan ko sa batch kan classic sa aga?"),
    (_i("Ube"), "ube batch sheet", "ang batch sheet ng ube", "ang batch sheet sa ube",
     "ang batch sheet sang ube", "an batch sheet han ube", "an batch sheet kan ube"),
    (_i("Special"), "how much sugar goes into the special?",
     "ilang asukal ang kailangan sa special?", "pila ka asukal ang kinahanglan sa special?",
     "pila ang asukal nga kinahanglan sa special?", "pira an asukal nga kinahanglan ha special?",
     "gurano an asukal na kaipuhan sa special?"),
    (_i("Salted egg"), "how many duck eggs for the salted egg batches?",
     "ilang itlog na maalat para sa batch ng salted egg?",
     "pila ka itlog nga maalat para sa batch sa salted egg?",
     "pila ka itlog nga maalat para sa batch sang salted egg?",
     "pira nga itlog nga maalat para ha batch han salted egg?",
     "pirang itlog na maalat para sa batch kan salted egg?"),
    (_i("Cheese overload"), "what's the batch cost for cheese overload?",
     "magkano ang gastos kada batch ng cheese overload?",
     "pila ang gasto matag batch sa cheese overload?",
     "pila ang gasto kada batch sang cheese overload?",
     "pira an gasto kada batch han cheese overload?",
     "magkano an gastos kada batch kan cheese overload?"),
    (_i("Puto bumbong"), "how many banana leaves for the puto bumbong?",
     "ilang dahon ng saging para sa puto bumbong?",
     "pila ka dahon sa saging para sa puto bumbong?",
     "pila ka dahon sang saging para sa puto bumbong?",
     "pira nga dahon han saging para ha puto bumbong?",
     "pirang dahon nin saging para sa puto bumbong?"),
    (_i("Classic"), "send the classic batch sheet", "ipadala ang batch sheet ng classic",
     "ipadala ang batch sheet sa classic", "ipadala ang batch sheet sang classic",
     "ipadara an batch sheet han classic", "ipadara an batch sheet kan classic"),
    (_i("Special"), "special ingredient list and cost per piece",
     "listahan ng sangkap ng special at gastos kada piraso",
     "lista sa sagol sa special ug gasto matag piraso",
     "listahan sang sangkap sang special kag gasto kada piraso",
     "listahan han sangkap han special ngan gasto kada piraso",
     "lista kan sangkap kan special asin gastos kada piraso"),
    (_i("Ube"), "how many trays of eggs for tomorrow's ube?", "ilang tray ng itlog para sa ube bukas?",
     "pila ka tray nga itlog para sa ube ugma?", "pila ka tray nga itlog para sa ube buwas?",
     "pira nga tray nga itlog para ha ube buwas?", "pirang tray na itlog para sa ube sa aga?"),
    (_i("Classic"), "cl batch sheet pls", "cl batch sheet po", "cl batch sheet palihug",
     "cl batch sheet palihog", "cl batch sheet alayon", "cl batch sheet tabi"),
]  # fmt: skip

F_RECIPE: list[Row] = [
    (_i("Classic"),
     "classic recipe update: 46 pcs, 2 kg flour, 1 tray eggs, 5 coco, 1 pack bl, 50 min",
     "update sa recipe ng classic: 46 piraso, 2 kg flour, 1 tray itlog, 5 niyog, 1 pack dahon, 50 min",
     ("update sa resipe sa classic: 46 piraso, 2 kg flour, 1 tray itlog, 5 niyog, 1 pack dahon,"
      " 50 minutos"),
     ("update sang resipe sang classic: 46 piraso, 2 kg flour, 1 tray itlog, 5 niyog, 1 pack"
      " dahon, 50 min"),
     ("update han resipe han classic: 46 piraso, 2 kg flour, 1 tray itlog, 5 niyog, 1 pack"
      " dahon, 50 minuto"),
     ("update kan resipe kan classic: 46 piraso, 2 kg flour, 1 tray itlog, 5 niyog, 1 pack"
      " dahon, 50 min")),
    (_i("Ube"), "ube: 36 pieces, 2 kg rice flour, 1 tray egg, 1 kg sugar, 6 coco, 55 min",
     "recipe ng ube: 36 piraso, 2 kg rice flour, 1 tray itlog, 1 kg asukal, 6 niyog, 55 min",
     "resipe sa ube: 36 piraso, 2 kg rice flour, 1 tray itlog, 1 kg asukal, 6 niyog, 55 minutos",
     "resipe sang ube: 36 piraso, 2 kilo rice flour, 1 tray itlog, 1 kilo asukal, 6 niyog, 55 min",
     "resipe han ube: 36 piraso, 2 kg rice flour, 1 tray itlog, 1 kg asukal, 6 niyog, 55 minutos",
     "resipe kan ube: 36 piraso, 2 kg rice flour, 1 tray itlog, 1 kg asukal, 6 niyog, 55 minuto"),
    (_i("Special"),
     "for the special: 40 pcs a batch, 2 kg rf, 1 tray egg, 1 kg sugar, 1 pack bl, 45 min",
     ("para sa special: 40 piraso bawat batch, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 45 min"),
     ("para sa special: 40 piraso matag batch, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 45 minutos"),
     ("para sa special: 40 piraso kada batch, 2 kg rf, 1 tray itlog, 1 kilo asukal, 1 pack"
      " dahon, 45 min"),
     ("para ha special: 40 piraso kada batch, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 45 minuto"),
     ("para sa special: 40 piraso kada batch, 2 kg rf, 1 tray itlog, 1 kg asukal, 1 pack bl,"
      " 45 minuto")),
    (_i("Salted egg"),
     "salted egg recipe: 36 pcs, 2 kg rf, 1 tray eggs, 10 maalat, 1 kg sugar, 45 min",
     "recipe ng salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 10 maalat, 1 kg asukal, 45 min",
     "resipe sa salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 10 maalat, 1 kg asukal, 45 minutos",
     "resipe sang salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 10 pula, 1 kg asukal, 45 min",
     "resipe han salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 10 pula, 1 kg asukal, 45 minuto",
     "resipe kan salted egg: 36 piraso, 2 kg rf, 1 tray itlog, 10 maalat, 1 kg asukal, 45 min"),
    (_i("Cheese overload"),
     "cheese overload: 32 pcs, 2 kg flour, 600 g cheese, 1 tray eggs, 1 kg sugar, 45 min",
     "cheese overload: 32 piraso, 2 kg flour, 600 g keso, 1 tray itlog, 1 kg asukal, 45 min",
     ("resipe sa cheese overload: 32 piraso, 2 kg flour, 600 g keso, 1 tray itlog, 1 kg asukal,"
      " 45 minutos"),
     ("resipe sang cheese overload: 32 piraso, 2 kg flour, 600 g keso, 1 tray itlog, 1 kg"
      " asukal, 45 min"),
     ("resipe han cheese overload: 32 piraso, 2 kg flour, 600 g keso, 1 tray itlog, 1 kg"
      " asukal, 45 minuto"),
     ("resipe kan cheese overload: 32 piraso, 2 kg flour, 600 g keso, 1 tray itlog, 1 kg"
      " asukal, 45 min")),
    (_i("Puto bumbong"),
     "puto bumbong: 50 pcs per batch, 3 kg rf, 1 kg sugar, 2 pack bl, 25 min",
     "puto bumbong: 50 piraso kada batch, 3 kg rf, 1 kg asukal, 2 pack dahon, 25 min",
     "puto bumbong: 50 piraso matag batch, 3 kg rf, 1 kg asukal, 2 pack dahon, 25 minutos",
     "puto bumbong: 50 piraso kada batch, 3 kg rf, 1 kilo asukal, 2 pack dahon, 25 min",
     "puto bumbong: 50 piraso kada batch, 3 kg rf, 1 kg asukal, 2 pack dahon, 25 minuto",
     "puto bumbong: 50 piraso kada batch, 3 kg rf, 1 kg asukal, 2 pack bl, 25 min"),
    (_i("Classic"), "cl recipe: 48 pcs, 2 kg rf, 1 tray egg, 6 niyog, 40 min",
     "recipe ng cl: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 40 min",
     "resipe sa cl: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 40 minutos",
     "resipe sang cl: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 40 min",
     "resipe han cl: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 40 minuto",
     "resipe kan cl: 48 piraso, 2 kg rf, 1 tray itlog, 6 niyog, 40 min"),
    (_i("Ube"),
     "save this for ube: 38 pcs, 2.5 kg rf, 1 tray eggs, 1 kg sugar, 1 pack bl, 50 min",
     ("i-save ito para sa ube: 38 piraso, 2.5 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 50 min"),
     ("i-save ni para sa ube: 38 piraso, 2.5 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 50 minutos"),
     ("i-save ini para sa ube: 38 piraso, 2.5 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 50 min"),
     ("i-save ini para ha ube: 38 piraso, 2.5 kg rf, 1 tray itlog, 1 kg asukal, 1 pack dahon,"
      " 50 minuto"),
     ("i-save ini para sa ube: 38 piraso, 2.5 kg rf, 1 tray itlog, 1 kg asukal, 1 pack bl,"
      " 50 min")),
    (_i("Special"), "special recipe, per batch: 36 pcs; 2 kg rf; 1 tray egg; 1 kg sugar; 45 min",
     "recipe ng special, kada batch: 36 piraso; 2 kg rf; 1 tray itlog; 1 kg asukal; 45 min",
     "resipe sa special, matag batch: 36 piraso; 2 kg rf; 1 tray itlog; 1 kg asukal; 45 minutos",
     "resipe sang special, kada batch: 36 piraso; 2 kg rf; 1 tray itlog; 1 kg asukal; 45 min",
     "resipe han special, kada batch: 36 piraso; 2 kg rf; 1 tray itlog; 1 kg asukal; 45 minuto",
     "resipe kan special, kada batch: 36 piraso; 2 kg rf; 1 tray itlog; 1 kg asukal; 45 min"),
    (_i("Classic"),
     ("new classic recipe: 52 pieces, 2 kg rice flour, 2 trays eggs, 6 coconut, 1 kg sugar,"
      " 45 mins"),
     ("bagong recipe ng classic: 52 piraso, 2 kg rice flour, 2 tray itlog, 6 niyog, 1 kg asukal,"
      " 45 minutos"),
     ("bag-ong resipe sa classic: 52 piraso, 2 kg rice flour, 2 tray itlog, 6 niyog, 1 kg"
      " asukal, 45 min"),
     ("bag-o nga resipe sang classic: 52 piraso, 2 kg rice flour, 2 tray itlog, 6 niyog, 1 kg"
      " asukal, 45 minuto"),
     ("bag-o nga resipe han classic: 52 piraso, 2 kg rice flour, 2 tray itlog, 6 niyog, 1 kg"
      " asukal, 45 minutos"),
     ("bagong resipe kan classic: 52 piraso, 2 kg rice flour, 2 tray itlog, 6 niyog, 1 kg"
      " asukal, 45 min")),
]  # fmt: skip

F_BATCH: list[Row] = [
    (_i("Classic"), "classic batch 1 done, 47 ok 1 burnt", "classic batch 1 tapos, 47 ok 1 sunog",
     "classic batch 1 human, 47 ok 1 nasunog", "classic batch 1 tapos na, 47 ok 1 nasunog",
     "classic batch 1 human na, 47 ok 1 nasunog", "classic batch 1 tapos na, 47 ok 1 nasunog tabi"),
    (_i("Ube"), "batch 3 ube: 35 good 1 dropped", "batch 3 ube: 35 maayos 1 nahulog",
     "batch 3 ube: 35 ok 1 nahulog", "batch 3 sang ube: 35 ok 1 nahulog",
     "batch 3 han ube: 35 ok 1 nahulog", "batch 3 kan ube: 35 ok 1 nahulog"),
    (_i("Special"), "special batch 2, 34 ok, 2 undercooked", "special batch 2, 34 ok, 2 hilaw",
     "special batch 2, 34 maayos, 2 hilaw", "special batch 2, 34 ok, 2 hilaw pa",
     "special batch 2, 34 ok, 2 hilaw la", "special batch 2, 34 ok, 2 hilaw tabi"),
    (_i("Salted egg"), "batch 2 salted egg 36 ok", "batch 2 salted egg 36 ok lahat",
     "batch 2 salted egg 36 ok tanan", "batch 2 sang salted egg 36 ok tanan",
     "batch 2 han salted egg 36 ok ngatanan", "batch 2 kan salted egg 36 ok gabos"),
    (_i("Cheese overload"), "batch 1 cheese overload: 33 good, 3 burnt",
     "batch 1 cheese overload: 33 maayos, 3 sunog", "batch 1 sa cheese overload: 33 ok, 3 nasunog",
     "batch 1 sang cheese overload: 33 ok, 3 nasunog",
     "batch 1 han cheese overload: 33 ok, 3 nasunog",
     "batch 1 kan cheese overload: 33 ok, 3 nasunog"),
    (_i("Puto bumbong"), "puto bumbong batch 2: 46 ok, 2 other", "puto bumbong batch 2: 46 ok, 2 iba",
     "puto bumbong batch 2: 46 ok, 2 uban", "puto bumbong batch 2: 46 ok, 2 iban",
     "puto bumbong batch 2: 46 ok, 2 iba pa", "puto bumbong batch 2: 46 ok, 2 iba na rason"),
    (_i("Classic"), "cl batch 5 48 ok", "cl batch 5 48 ok lahat", "cl batch 5 48 ok tanan",
     "cl batch 5 48 ok tanan na", "cl batch 5 48 ok ngatanan", "cl batch 5 48 ok gabos"),
    (_i("Ube"), "done with ube batch 4: 36 ok", "tapos ang ube batch 4: 36 ok",
     "human na ang ube batch 4: 36 ok", "tapos na ang ube batch 4: 36 ok",
     "human na an ube batch 4: 36 ok", "tapos na an ube batch 4: 36 ok"),
    (_i("Special"), "batch no. 3 special: 35 ok 1 dropped", "batch no. 3 special: 35 ok 1 nahulog",
     "batch no. 3 sa special: 35 ok 1 nahulog", "batch no. 3 sang special: 35 ok 1 nahulog",
     "batch no. 3 han special: 35 ok 1 nahulog", "batch no. 3 kan special: 35 ok 1 nahulog"),
    (_i("Classic"), "batch 6 classic 44 pcs ok 4 undercooked", "batch 6 classic 44 piraso ok 4 hilaw",
     "batch 6 sa classic 44 piraso ok 4 hilaw", "batch 6 sang classic 44 piraso ok 4 hilaw",
     "batch 6 han classic 44 piraso ok 4 hilaw", "batch 6 kan classic 44 piraso ok 4 hilaw"),
]  # fmt: skip

# Each names the delivery or the dispatch, so it is never the plan question.
F_DISPATCH: list[Row] = [
    (NONE, "what's on tomorrow's delivery to us?", "ano ang laman ng delivery sa amin bukas?",
     "unsa ang sulod sa delivery namo ugma?", "ano ang sulod sang delivery sa amon buwas?",
     "ano an sulod han delivery ha amon buwas?", "ano an laog kan delivery samo sa aga?"),
    (NONE, "what's the commissary delivering to the Mall kiosk tomorrow?",
     "ano ang ide-deliver ng commissary sa Mall kiosk bukas?",
     "unsa ang i-deliver sa commissary sa Mall kiosk ugma?",
     "ano ang i-deliver sang commissary sa Mall kiosk buwas?",
     "ano an ide-deliver han commissary ha Mall kiosk buwas?",
     "ano an ide-deliver kan commissary sa Mall kiosk sa aga?"),
    (NONE, "how many trays arrive with tomorrow's delivery?",
     "ilang tray ang darating sa delivery bukas?", "pila ka tray ang moabot sa delivery ugma?",
     "pila ka tray ang maabot sa delivery buwas?", "pira nga tray an maabot ha delivery buwas?",
     "pirang tray an maabot sa delivery sa aga?"),
    (NONE, "dispatch for the Mall kiosk, please", "dispatch para sa Mall kiosk po",
     "dispatch para sa Mall kiosk palihug", "dispatch para sa Mall kiosk palihog",
     "dispatch para ha Mall kiosk alayon", "dispatch para sa Mall kiosk tabi"),
    (NONE, "how many classic pieces are on our delivery?",
     "ilang piraso ng classic ang nasa delivery namin?",
     "pila ka piraso sa classic ang naa sa among delivery?",
     "pila ka piraso sang classic ang yara sa amon delivery?",
     "pira nga piraso han classic an aadi ha amon delivery?",
     "pirang piraso kan classic an yaon sa samong delivery?"),
    (NONE, "what comes on the next delivery?", "ano ang darating sa susunod na delivery?",
     "unsa ang moabot sa sunod nga delivery?", "ano ang maabot sa masunod nga delivery?",
     "ano an maabot ha sunod nga delivery?", "ano an maabot sa masunod na delivery?"),
    (NONE, "is the dispatch for our kiosk packed yet?",
     "naka-pack na ba ang dispatch para sa kiosk namin?",
     "naka-pack na ba ang dispatch para sa among kiosk?",
     "naka-pack na bala ang dispatch para sa amon kiosk?",
     "naka-pack na ba an dispatch para ha amon kiosk?",
     "naka-pack na daw an dispatch para sa samong kiosk?"),
    (NONE, "how many pieces come on our delivery tomorrow?",
     "ilang piraso ang darating sa delivery namin bukas?",
     "pila ka piraso ang moabot sa among delivery ugma?",
     "pila ka piraso ang maabot sa amon delivery buwas?",
     "pira nga piraso an maabot ha amon delivery buwas?",
     "pirang piraso an maabot sa samong delivery sa aga?"),
    (NONE, "send the Mall kiosk delivery list", "ipadala ang listahan ng delivery ng Mall kiosk",
     "ipadala ang lista sa delivery sa Mall kiosk",
     "ipadala ang listahan sang delivery sang Mall kiosk",
     "ipadara an listahan han delivery han Mall kiosk",
     "ipadara an lista kan delivery kan Mall kiosk"),
    (NONE, "when does our delivery arrive tomorrow?",
     "anong oras darating ang delivery namin bukas?",
     "unsang orasa moabot ang among delivery ugma?",
     "ano nga oras maabot ang amon delivery buwas?",
     "ano nga oras maabot an amon delivery buwas?",
     "anong oras maabot an samong delivery sa aga?"),
]  # fmt: skip

F_DELIVERED: list[Row] = [
    (MALL, "Mall kiosk delivery done", "tapos ang delivery sa Mall kiosk",
     "human ang delivery sa Mall kiosk", "tapos na ang delivery sang Mall kiosk",
     "human na an delivery han Mall kiosk", "tapos na an delivery kan Mall kiosk"),
    (STALL, "street stall received the trays", "natanggap na ng street stall ang mga tray",
     "nadawat na sa street stall ang mga tray", "nabaton na sang street stall ang mga tray",
     "nakarawat na han street stall an mga tray", "naako na kan street stall an mga tray"),
    (MALL, "dropped everything at the mall kiosk", "naibaba ko na lahat sa mall kiosk",
     "nahatod na nako tanan sa mall kiosk", "naihatod ko na tanan sa mall kiosk",
     "naihatod ko na ngatanan ha mall kiosk", "naitao ko na gabos sa mall kiosk"),
    (STALL, "Berto here, street stall delivered", "si Berto ito, delivered na ang street stall",
     "si Berto ni, nahatod na ang street stall", "si Berto ini, naihatod na ang street stall",
     "hi Berto ini, naihatod na an street stall", "si Berto ini, naitao na an street stall"),
    (MALL, "at the mall kiosk now, delivery handed over",
     "nandito na sa mall kiosk, naiabot na ang delivery",
     "ania na sa mall kiosk, nahatag na ang delivery",
     "ari na ako sa mall kiosk, naentrega na ang delivery",
     "aadi na ha mall kiosk, naentrega na an delivery",
     "yaon na sa mall kiosk, naentrega na an delivery"),
    (STALL, "stall delivery complete", "kumpleto na ang delivery sa stall",
     "kompleto na ang delivery sa stall", "kompleto na gid ang delivery sa stall",
     "kompleto na an delivery ha stall", "kumpleto na an delivery sa stall"),
    (MALL, "mall: delivered, all trays", "mall: naihatid na, lahat ng tray",
     "mall: nahatod na, tanan nga tray", "mall: naihatod na, tanan nga tray",
     "mall: naihatod na, ngatanan nga tray", "mall: naitao na, gabos na tray"),
    (STALL, "done at the street stall, delivered", "tapos sa street stall, naihatid na",
     "human sa street stall, nahatod na", "tapos sa street stall, naihatod na",
     "human ha street stall, naihatod na", "tapos sa street stall, naitao na"),
    (MALL, "the Mall kiosk got its delivery", "natanggap na ng Mall kiosk ang delivery nila",
     "nadawat na sa Mall kiosk ang ilang delivery", "nabaton na sang Mall kiosk ang ila delivery",
     "nakarawat na han Mall kiosk an ira delivery", "naako na kan Mall kiosk an saindang delivery"),
    (STALL, "unloaded at the street stall, all good", "nai-unload na sa street stall, ayos lahat",
     "na-unload na sa street stall, okay tanan", "na-unload na sa street stall, okay tanan na",
     "na-unload na ha street stall, okay ngatanan", "na-unload na sa street stall, okay gabos"),
]  # fmt: skip

F_CAPACITY: list[Row] = [
    (_i("Classic", number=250), "room in the ovens for 250 classic on Dec 20?",
     "may puwang pa ba sa oven para sa 250 classic sa Dec 20?",
     "naa pa bay lugar sa oven para sa 250 classic sa Dec 20?",
     "may lugar pa bala ang oven para sa 250 classic sa Dec 20?",
     "may-ada pa ba lugar an oven para ha 250 classic ha Dec 20?",
     "may lugar pa daw an oven para sa 250 classic sa Dec 20?"),
    (_i("Ube", number=90), "could we bake 90 ube on Friday?",
     "makakaluto ba tayo ng 90 ube sa Biyernes?", "makaluto ba ta og 90 ube sa Biyernes?",
     "makaluto bala kita sang 90 ube sa Biyernes?", "makakaluto ba kita hin 90 ube ha Biyernes?",
     "makakaluto daw kita nin 90 ube sa Biyernes?"),
    (_i("Special", number=200), "how about 200 special on Dec 24, will it fit?",
     "200 special sa Dec 24, kakasya ba?", "200 special sa Dec 24, mosulod ba?",
     "200 special sa Dec 24, masulod bala?", "200 special ha Dec 24, masulod ba?",
     "200 special sa Dec 24, makakalaog daw?"),
    (_i("Salted egg", number=48), "48 salted egg on Saturday, enough oven time?",
     "48 salted egg sa Sabado, may oras pa ba ang oven?",
     "48 salted egg sa Sabado, naa pa bay oras ang oven?",
     "48 salted egg sa Sabado, may oras pa bala ang oven?",
     "48 salted egg ha Sabado, may-ada pa ba oras an oven?",
     "48 salted egg sa Sabado, igwa pa daw oras an oven?"),
    (_i("Cheese overload", number=80), "is there oven time for 80 cheese overload on Dec 30?",
     "may oras pa ba ang oven para sa 80 cheese overload sa Dec 30?",
     "naa pa bay oras ang oven para sa 80 cheese overload sa Dec 30?",
     "may oras pa bala ang oven para sa 80 cheese overload sa Dec 30?",
     "may-ada pa ba oras an oven para ha 80 cheese overload ha Dec 30?",
     "igwa pa daw oras an oven para sa 80 cheese overload sa Dec 30?"),
    (_i("Puto bumbong", number=120), "can we squeeze in 120 puto bumbong on Dec 25?",
     "maisisingit pa ba ang 120 puto bumbong sa Dec 25?",
     "masal-ot pa ba ang 120 puto bumbong sa Dec 25?",
     "masulod pa bala ang 120 puto bumbong sa Dec 25?",
     "masulod pa ba an 120 puto bumbong ha Dec 25?",
     "masingit pa daw an 120 puto bumbong sa Dec 25?"),
    (_i("Classic", number=4), "can the ovens do 4 batches of classic on Saturday?",
     "kaya ba ng oven ang 4 batch ng classic sa Sabado?",
     "kaya ba sa oven ang 4 ka batch sa classic sa Sabado?",
     "kaya bala sang oven ang 4 ka batch sang classic sa Sabado?",
     "kaya ba han oven an 4 nga batch han classic ha Sabado?",
     "kaya daw kan oven an 4 na batch kan classic sa Sabado?"),
    (_i("Ube", number=150), "150 ube for a party on Dec 19, doable?",
     "150 ube para sa party sa Dec 19, kaya ba?", "150 ube para sa party sa Dec 19, makaya ba?",
     "150 ube para sa party sa Dec 19, masarangan bala?",
     "150 ube para ha party ha Dec 19, kaya ba?", "150 ube para sa party sa Dec 19, kaya daw?"),
    (_i("Special", number=100), "do the ovens have space for 100 special on Sunday?",
     "may espasyo pa ba ang oven para sa 100 special sa Linggo?",
     "naa pa bay espasyo ang oven para sa 100 special sa Domingo?",
     "may espasyo pa bala ang oven para sa 100 special sa Domingo?",
     "may-ada pa ba espasyo an oven para ha 100 special ha Domingo?",
     "igwa pa daw espasyo an oven para sa 100 special sa Domingo?"),
    (_i("Classic", number=360), "will 360 classic fit in the ovens on Dec 23?",
     "kakasya ba sa oven ang 360 classic sa Dec 23?", "masulod ba sa oven ang 360 classic sa Dec 23?",
     "masulod bala sa oven ang 360 classic sa Dec 23?",
     "masulod ba ha oven an 360 classic ha Dec 23?",
     "makakalaog daw sa oven an 360 classic sa Dec 23?"),
]  # fmt: skip

HEAD, OWNER, DRIVER, KIOSK = "head", "owner", "driver", "kiosk"
# scenario: (spec scenario, expected action, sender role, spent rows)
SCENARIOS: dict[str, tuple[int, str, str, list[Row]]] = {
    "plan": (1, "plan", HEAD, PLAN),
    "confirm": (1, "confirm_plan", HEAD, CONFIRM),
    "orders": (2, "plan", HEAD, ORDERS),
    "change": (3, "change_plan", HEAD, CHANGE),
    "batch_sheet": (4, "batch_sheet", HEAD, BATCH_SHEET),
    "recipe": (5, "set_recipe", OWNER, RECIPE),
    "batch": (6, "record_batch", HEAD, BATCH),
    "dispatch": (7, "dispatch", KIOSK, DISPATCH),
    "delivered": (7, "delivered", DRIVER, DELIVERED),
    "capacity": (9, "capacity", OWNER, CAPACITY),
}
# scenario: its fresh rows
FRESH: dict[str, list[Row]] = {
    "plan": F_PLAN,
    "confirm": F_CONFIRM,
    "orders": F_ORDERS,
    "change": F_CHANGE,
    "batch_sheet": F_BATCH_SHEET,
    "recipe": F_RECIPE,
    "batch": F_BATCH,
    "dispatch": F_DISPATCH,
    "delivered": F_DELIVERED,
    "capacity": F_CAPACITY,
}

ASK, CLERK = "ask", "clerk"
# The short half (D42): (language, sender role, text, expected action or "ask", expected)
SHORT: list[tuple[str, str, str, str, dict[str, Any]]] = [
    ("en", HEAD, "plan tmrw", "plan", NONE),
    ("en", HEAD, "add 1 batch ube", "change_plan", _i("Ube", number=1)),
    ("en", HEAD, "less classic 2 batch", "change_plan", _i("Classic", number=2)),
    ("en", OWNER, "plan ok go", "confirm_plan", NONE),
    ("en", HEAD, "batch sheet sp", "batch_sheet", _i("Special")),
    ("en", HEAD, "batch2 cl 45 ok 3 burnt", "record_batch", _i("Classic")),
    ("en", HEAD, "recipe ube 36 pcs 2kg flour", "set_recipe", _i("Ube")),
    ("en", DRIVER, "delivered mall", "delivered", NONE),
    ("en", CLERK, "whats coming to mall", "dispatch", NONE),
    ("en", OWNER, "capacity 200 cl dec 24", "capacity", _i("Classic", number=200)),
    ("en", HEAD, "ube 2", ASK, _i("Ube", number=2)),
    ("en", DRIVER, "done", ASK, NONE),
    ("fil", HEAD, "ano lutuin bukas", "plan", NONE),
    ("fil", HEAD, "dagdag 1 batch se", "change_plan", _i("Salted egg", number=1)),
    ("fil", HEAD, "bawas ube 1 batch", "change_plan", _i("Ube", number=1)),
    ("fil", OWNER, "sige go na plano", "confirm_plan", NONE),
    ("fil", HEAD, "ilang itlog para sa cl", "batch_sheet", _i("Classic")),
    ("fil", HEAD, "batch1 sp 40 ok 2 sunog", "record_batch", _i("Special")),
    ("fil", HEAD, "recipe se 36 piraso 45 min", "set_recipe", _i("Salted egg")),
    ("fil", DRIVER, "hatid na sa street po", "delivered", NONE),
    ("fil", CLERK, "ano dadalhin samin bukas", "dispatch", NONE),
    ("fil", OWNER, "kaya ba 150 ube sab", "capacity", _i("Ube", number=150)),
    ("fil", HEAD, "classic 3", ASK, _i("Classic", number=3)),
    ("fil", DRIVER, "ok na po", ASK, NONE),
]


def _cases() -> list[Case]:
    """The spent rows (half "spent"), the fresh rows (even seeds tune, odd seeds gate), then
    the short half."""
    return [
        Case(lang, scenario, text, action, role,
             previous=DRAFT[lang] if scenario == "confirm" else "",
             half=half or ("tune" if n % 2 == 0 else "gate"), expected=expected)
        for half, rows_of in (("spent", {s: v[3] for s, v in SCENARIOS.items()}), (None, FRESH))
        for scenario, (_, action, role, _) in SCENARIOS.items()
        for n, (expected, *texts) in enumerate(rows_of[scenario])
        for lang, text in zip(GATED_LANGS, texts, strict=True)
    ] + [
        Case(lang, "short", text, action, role, half="short", expected=expected)
        for lang, role, text, action, expected in SHORT
    ]  # fmt: skip


CASES: list[Case] = _cases()
