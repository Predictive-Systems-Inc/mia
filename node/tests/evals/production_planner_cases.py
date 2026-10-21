"""The production planner decider eval set (spec 2026-10-21-production-planner, scenarios 1 to 7
and 9 as chat asks): what the commissary head, the owner, the driver and a kiosk supervisor
send, ten messages per scenario in each gated language. Data only;
test_production_planner_evals.py runs it.

Scenario 1 is two asks (the plan, and "ok" answering the draft plan), scenario 7 two (a kiosk
supervisor's "ano ang darating" and the driver's delivered); scenario 2 (confirmed orders in
the plan) is asked as the plan. Halves by seed: the even seeds of a scenario are the tune half,
the odd seeds the gate half, and a seed's languages share a half (no text in both halves, shape
test).

Synthetic, written by Claude, not native speakers (D18). English seeds come first; the five
Philippine languages are drafts for commissary and kiosk staff texting on a phone, and Q28 to
Q35 cover their review. The run pins today to TODAY (PP_TODAY, a Tuesday) with tomorrow's plan
drafted, so "bukas", "ugma", "buwas" and "sa aga" name the plan's date. Code reads every value
Jev picks (rule 7), and the shape test checks it: each expected number is a words.numbers
candidate, each batch report a words.batch parse, each recipe a full words.recipe parse (one
part per comma, units and short codes code knows), and each added or removed item a line of
the drafted plan. No change text names "today" (subong, karon, yana), which would ask for the
plan of another day."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str  # an ACTIONS key
    role: str  # head (Nonoy, the commissary), owner (Rosa), driver (Berto), kiosk (Marites)
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "gate"] = "tune"
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

# Mia's draft plan message, the previous message of every CONFIRM case.
DRAFT: dict[str, str] = {
    "en": "Tomorrow's draft plan: Classic 3 batches (144 pcs), Special 2 batches (72), Ube 1"
    " batch (36). Reply ok to confirm.",
    "fil": "Draft na plano para bukas: Classic 3 batch (144 piraso), Special 2 batch (72), Ube 1"
    " batch (36). Sumagot ng ok para i-confirm.",
    "ceb": "Draft nga plano para ugma: Classic 3 ka batch (144 ka piraso), Special 2 ka batch"
    " (72), Ube 1 ka batch (36). Tubaga og ok aron i-confirm.",
    "hil": "Draft nga plano para buwas: Classic 3 ka batch (144 ka piraso), Special 2 ka batch"
    " (72), Ube 1 ka batch (36). Sabta sang ok para i-confirm.",
    "war": "Draft nga plano para buwas: Classic 3 nga batch (144 nga piraso), Special 2 nga"
    " batch (72), Ube 1 nga batch (36). Bales hin ok para i-confirm.",
    "bcl": "Draft na plano para sa aga: Classic 3 na batch (144 na piraso), Special 2 na batch"
    " (72), Ube 1 na batch (36). Simbagan nin ok tanganing i-confirm.",
}

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

HEAD, OWNER, DRIVER, KIOSK = "head", "owner", "driver", "kiosk"
# scenario: (spec scenario, expected action, sender role, rows)
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


def _cases() -> list[Case]:
    return [
        Case(lang, scenario, text, action, role,
             previous=DRAFT[lang] if scenario == "confirm" else "",
             half="tune" if n % 2 == 0 else "gate", expected=expected)
        for scenario, (_, action, role, rows) in SCENARIOS.items()
        for n, (expected, *texts) in enumerate(rows)
        for lang, text in zip(GATED_LANGS, texts, strict=True)
    ]  # fmt: skip


CASES: list[Case] = _cases()
