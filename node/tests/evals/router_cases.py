"""The router eval set (spec 2026-10-18, Testing): the shift supervisor intent test split, the
270 language spike messages and sixty switch cases. Data only; test_router_eval.py runs it."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Case:
    lang: str
    text: str
    expected: str  # an agent id, or "any" (a greeting or thanks: any agent is right)
    active: str | None = None
    previous: str = ""
    group: str = "single"  # single | switch | follow_up


# Synthetic, written by Claude, not native speakers (D18). From the 2026-10-18 language spike.
# Labels: (id, kind, item, reason). Same order in every language.
LABELS = [
    ("R1", "report", "bo", None),
    ("R2", "report", "pb", None),
    ("R3", "report", "bcu", None),
    ("R4", "report", "bc4", None),
    ("R5", "report", "bhc", None),
    ("R6", "report", "sb", None),
    ("R7", "report", "fpb", None),
    ("R8", "report", "cbs", None),
    ("R9", "report", "pbc", None),
    ("R10", "report", "esb", None),
    ("S1", "stock", "pb", None),
    ("S2", "stock", "bcu", None),
    ("S3", "stock", "fb", None),
    ("S4", "stock", "bchc", None),
    ("S5", "stock", "bo", None),
    ("Q1", "question", None, None),
    ("Q2", "question", None, None),
    ("Q3", "other", None, None),
    ("Q4", "other", None, None),
    ("Q5", "other", None, None),
    ("W1", None, None, "technique"),
    ("W2", None, None, "technique"),
    ("W3", None, None, "technique"),
    ("W4", None, None, "busy_event"),
    ("W5", None, None, "busy_event"),
    ("W6", None, None, "big_order"),
    ("W7", None, None, "big_order"),
    ("W8", None, None, "weather"),
    ("W9", None, None, "weather"),
    ("W10", None, None, "other"),
]

TEXTS = {
    "en": [
        "Sold 5 Overload so far",
        "We sold 12 classic puto bumbong today",
        "8 ube bibingcute sold",
        "3 boxes of four bibingcute were bought this morning",
        "Ham and cheese bibingka, 6 pieces sold",
        "Only 2 special bibingka sold today",
        "Frozen puto bumbong: 4 sold",
        "We sold 10 classic bibingka with salted egg",
        "7 puto bumbong with cheese sold",
        "Extra super bibingka, 9 sold",
        "The puto bumbong is sold out",
        "We ran out of ube",
        "Only 2 frozen bibingka left",
        "No more ham and cheese bibingcute",
        "Overload is almost gone",
        "What is today's target?",
        "How much have we sold so far?",
        "Good morning!",
        "Thank you, Mia",
        "I will be late tomorrow",
        "I offered puto bumbong to every customer who bought bibingka",
        "I smiled and greeted everyone who passed by",
        "I suggested the box of four instead of one piece",
        "It was payday so many people came",
        "There was a mass at the church nearby and people came after",
        "An office ordered 20 boxes for their party",
        "One customer bought 15 pieces for the family reunion",
        "It was raining so people wanted something warm",
        "It was cool weather today, perfect for bibingka",
        "I don't know, maybe luck",
    ],
    "fil": [
        "Nakabenta na ako ng 5 Overload",
        "12 classic puto bumbong ang nabenta namin ngayon",
        "8 ube bibingcute ang nabenta",
        "3 kahon ng bibingcute na tig-apat ang nabili kaninang umaga",
        "Bibingka na ham and cheese, 6 piraso ang nabenta",
        "2 special bibingka lang ang nabenta ngayon",
        "Frozen puto bumbong: 4 ang nabenta",
        "Nakabenta kami ng 10 classic bibingka na may itlog na maalat",
        "7 puto bumbong na may keso ang nabenta",
        "Extra super bibingka, 9 ang nabenta",
        "Ubos na ang puto bumbong",
        "Naubusan kami ng ube",
        "2 na lang ang natitirang frozen bibingka",
        "Wala nang bibingcute na ham and cheese",
        "Malapit nang maubos ang Overload",
        "Ano ang target natin ngayong araw?",
        "Magkano na ang nabenta natin?",
        "Magandang umaga!",
        "Salamat, Mia",
        "Male-late ako bukas",
        "Inalok ko ng puto bumbong ang bawat bumili ng bibingka",
        "Ngumiti ako at binati ko ang lahat ng dumaan",
        "Iminungkahi ko ang kahon ng apat imbes na isang piraso",
        "Sweldo kasi kaya maraming tao",
        "May misa sa simbahan sa tabi kaya dumagsa ang tao pagkatapos",
        "May opisinang umorder ng 20 kahon para sa party nila",
        "May isang customer na bumili ng 15 piraso para sa reunion ng pamilya",
        "Umuulan kaya gusto ng mga tao ng mainit",
        "Malamig ang panahon ngayon, swak sa bibingka",
        "Ewan ko, baka swerte lang",
    ],
    "ceb": [
        "Nakabaligya na kog 5 ka Overload",
        "12 ka classic puto bumbong ang nahalin namo karon",
        "8 ka ube bibingcute ang nahalin",
        "3 ka kahon sa bibingcute nga tag-upat ang napalit ganinang buntag",
        "Bibingka nga ham and cheese, 6 ka buok ang nahalin",
        "2 ra ka special bibingka ang nahalin karon",
        "Frozen puto bumbong: 4 ang nahalin",
        "Nakabaligya mi og 10 ka classic bibingka nga naay itlog nga maalat",
        "7 ka puto bumbong nga naay keso ang nahalin",
        "Extra super bibingka, 9 ang nahalin",
        "Nahurot na ang puto bumbong",
        "Nahutdan mi og ube",
        "2 na lang ang nabilin nga frozen bibingka",
        "Wala nay bibingcute nga ham and cheese",
        "Hapit na mahurot ang Overload",
        "Unsa man ang atong target karong adlawa?",
        "Pila na man ang atong nahalin?",
        "Maayong buntag!",
        "Salamat, Mia",
        "Ma-late ko ugma",
        "Gi-offer nako og puto bumbong ang matag usa nga mipalit og bibingka",
        "Mipahiyom ko ug gi-greet nako ang tanan nga miagi",
        "Gisugyot nako ang kahon nga upat imbes usa ra ka buok",
        "Sweldo man gud mao daghang tawo",
        "Naay misa sa simbahan duol mao nidagsa ang tawo human",
        "Naay opisina nga ni-order og 20 ka kahon para sa ilang party",
        "Naay usa ka customer nga mipalit og 15 ka buok para sa reunion sa pamilya",
        "Nag-ulan man mao gusto sa mga tawo og init",
        "Bugnaw ang panahon karon, haom sa bibingka",
        "Ambot, swerte ra tingali",
    ],
    "ilo": [
        "Nakailako metten iti 5 nga Overload",
        "12 a classic puto bumbong ti nailakomi ita",
        "8 nga ube bibingcute ti nailako",
        "3 a kahon ti bibingcute nga tig-uppat ti nagatang idi bigat",
        "Bibingka a ham and cheese, 6 a piraso ti nailako",
        "2 laeng a special bibingka ti nailako ita",
        "Frozen puto bumbong: 4 ti nailako",
        "Nakailakokami iti 10 a classic bibingka nga addaan itlog nga maalat",
        "7 a puto bumbong nga addaan keso ti nailako",
        "Extra super bibingka, 9 ti nailako",
        "Naibus ti puto bumbong",
        "Naibusankami iti ube",
        "2 laengen ti nabati a frozen bibingka",
        "Awanen ti bibingcute a ham and cheese",
        "Asideg nga maibus ti Overload",
        "Ania ti target tayo ita nga aldaw?",
        "Mano ti nailakotayon?",
        "Naimbag a bigat!",
        "Agyamanak, Mia",
        "Ma-late-ak inton bigat",
        "Indiaya ko ti puto bumbong iti tunggal gimmatang iti bibingka",
        "Immisemak ken kinablaaw ko ti amin a limmabas",
        "Insingasing ko ti kahon nga uppat imbes a maysa a piraso",
        "Sueldo ngamin isu nga adu ti tao",
        "Adda misa iti simbaan iti asideg isu nga immadu ti tao kalpasanna",
        "Adda opisina nga nag-order iti 20 a kahon para iti partida da",
        "Adda maysa a customer a gimmatang iti 15 a piraso para iti reunion ti pamilia",
        "Agtudtudo isu a kayat dagiti tao ti nabara",
        "Nalamiis ti panawen ita, nasayaat para iti bibingka",
        "Diak ammo, gasat la nalabit",
    ],
    "hil": [
        "Nakabaligya na ko sang 5 ka Overload",
        "12 ka classic puto bumbong ang nabaligya namon subong",
        "8 ka ube bibingcute ang nabaligya",
        "3 ka kahon sang bibingcute nga tig-apat ang ginbakal kaina aga",
        "Bibingka nga ham and cheese, 6 ka buok ang nabaligya",
        "2 lang ka special bibingka ang nabaligya subong",
        "Frozen puto bumbong: 4 ang nabaligya",
        "Nakabaligya kami sang 10 ka classic bibingka nga may itlog nga maalat",
        "7 ka puto bumbong nga may keso ang nabaligya",
        "Extra super bibingka, 9 ang nabaligya",
        "Ubos na ang puto bumbong",
        "Naubusan kami sang ube",
        "2 na lang ang nabilin nga frozen bibingka",
        "Wala na sang bibingcute nga ham and cheese",
        "Malapit na maubos ang Overload",
        "Ano ang aton target subong nga adlaw?",
        "Pila na ang aton nabaligya?",
        "Maayong aga!",
        "Salamat, Mia",
        "Ma-late ako buwas",
        "Gin-offer ko sang puto bumbong ang kada isa nga nagbakal sang bibingka",
        "Nagyuhom ako kag gin-greet ko ang tanan nga nag-agi",
        "Ginsugest ko ang kahon nga apat imbes isa lang ka buok",
        "Sweldo kay gani madamo tawo",
        "May misa sa simbahan malapit gani nagdagsa ang tawo pagkatapos",
        "May opisina nga nag-order sang 20 ka kahon para sa ila party",
        "May isa ka customer nga nagbakal sang 15 ka buok para sa reunion sang pamilya",
        "Nagaulan gani gusto sang mga tawo ang mainit",
        "Matugnaw ang panahon subong, bagay sa bibingka",
        "Ambot, swerte lang siguro",
    ],
    "war": [
        "Nakabaligya na ako hin 5 nga Overload",
        "12 nga classic puto bumbong an nabaligya namon yana",
        "8 nga ube bibingcute an nabaligya",
        "3 nga kahon han bibingcute nga tig-upat an ginpalit kanina aga",
        "Bibingka nga ham and cheese, 6 ka buok an nabaligya",
        "2 la nga special bibingka an nabaligya yana",
        "Frozen puto bumbong: 4 an nabaligya",
        "Nakabaligya kami hin 10 nga classic bibingka nga may itlog nga maalat",
        "7 nga puto bumbong nga may keso an nabaligya",
        "Extra super bibingka, 9 an nabaligya",
        "Ubos na an puto bumbong",
        "Naubusan kami hin ube",
        "2 na la an nahibilin nga frozen bibingka",
        "Waray na bibingcute nga ham and cheese",
        "Hirani na maubos an Overload",
        "Ano an aton target yana nga adlaw?",
        "Pira na an aton nabaligya?",
        "Maupay nga aga!",
        "Salamat, Mia",
        "Ma-late ako buwas",
        "Gin-offer ko hin puto bumbong an kada usa nga namalit hin bibingka",
        "Nagpahiyum ako ngan gin-greet ko an ngatanan nga naagi",
        "Ginsugest ko an kahon nga upat imbes usa la ka buok",
        "Sweldo man gud salit damu an tawo",
        "May misa ha simbahan harani salit nagdagsa an tawo katapos",
        "May opisina nga nag-order hin 20 nga kahon para han ira party",
        "May usa nga customer nga namalit hin 15 ka buok para han reunion han pamilya",
        "Nauran salit karuyag han mga tawo an mainit",
        "Mahagkot an panahon yana, bagay ha bibingka",
        "Ambot, swerte la siguro",
    ],
    "bcl": [
        "Nakapabakal na ako nin 5 na Overload",
        "12 na classic puto bumbong an napabakal mi ngonyan",
        "8 na ube bibingcute an napabakal",
        "3 na kahon kan bibingcute na tig-apat an binakal kaninang aga",
        "Bibingka na ham and cheese, 6 na piraso an napabakal",
        "2 sana na special bibingka an napabakal ngonyan",
        "Frozen puto bumbong: 4 an napabakal",
        "Nakapabakal kami nin 10 na classic bibingka na igwang itlog na maalat",
        "7 na puto bumbong na igwang keso an napabakal",
        "Extra super bibingka, 9 an napabakal",
        "Ubos na an puto bumbong",
        "Naubusan kami nin ube",
        "2 na sana an natada na frozen bibingka",
        "Mayo nang bibingcute na ham and cheese",
        "Harani nang maubos an Overload",
        "Ano an target ta ngonyan na aldaw?",
        "Pira na an napabakal ta?",
        "Marhay na aga!",
        "Dios mabalos, Mia",
        "Ma-late ako sa aga",
        "Inalok ko nin puto bumbong an lambang nagbakal nin bibingka",
        "Nagngirit ako asin binati ko an gabos na nag-agi",
        "Sinuhestiyon ko an kahon na apat imbes na saro sanang piraso",
        "Sueldo kaya dakol an tawo",
        "May misa sa simbahan na harani kaya nagdagsa an tawo pagkatapos",
        "May opisina na nag-order nin 20 na kahon para sa saindang party",
        "May sarong customer na nagbakal nin 15 na piraso para sa reunion kan pamilya",
        "Nag-uuran kaya gusto kan mga tawo an mainit",
        "Malipot an panahon ngonyan, swak sa bibingka",
        "Ewan ko, baka swerte sana",
    ],
    "pam": [
        "Mekapagbenta naku 5 a Overload",
        "12 a classic puto bumbong ing mebenta mi ngeni",
        "8 a ube bibingcute ing mebenta",
        "3 a kahon ning bibingcute a tig-apat ing sinali kanina abak",
        "Bibingka a ham and cheese, 6 a buri ing mebenta",
        "2 mu a special bibingka ing mebenta ngeni",
        "Frozen puto bumbong: 4 ing mebenta",
        "Mekapagbenta kami 10 a classic bibingka a atin itlog a maalat",
        "7 a puto bumbong a atin keso ing mebenta",
        "Extra super bibingka, 9 ing mebenta",
        "Mebus ne ing puto bumbong",
        "Mebusan kami ube",
        "2 na mu ing natira a frozen bibingka",
        "Ala nang bibingcute a ham and cheese",
        "Malapit neng mebus ing Overload",
        "Nanu ing target tamu ngeni a aldo?",
        "Magkanu na ing mebenta tamu?",
        "Mayap a abak!",
        "Salamat, Mia",
        "Ma-late ku bukas",
        "Ingalok ku puto bumbong ing balang sinali bibingka",
        "Megngiti ku at binati ku ing eganagana a linabas",
        "Sinuggest ku ing kahon a apat imbes a metung a buri",
        "Sweldo kasi kaya dakal a tau",
        "Atin misa king simbahan malapit kaya dinagsa ing tau kaibat",
        "Atin opisina a nag-order 20 a kahon para king party da",
        "Atin metung a customer a sinali 15 a buri para king reunion ning pamilya",
        "Muran kaya buri da ding tau ing mainit",
        "Malamig ing panaun ngeni, bagay king bibingka",
        "Ewan ku, swerte mu siguru",
    ],
    "pag": [
        "Akapanlako la ak na 5 ya Overload",
        "12 ya classic puto bumbong so nilako mi natan",
        "8 ya ube bibingcute so nilako",
        "3 ya kahon na bibingcute ya tig-apat so ingaton ed kabuasan",
        "Bibingka ya ham and cheese, 6 ya piraso so nilako",
        "2 labat ya special bibingka so nilako natan",
        "Frozen puto bumbong: 4 so nilako",
        "Akapanlako kami na 10 ya classic bibingka ya walay itlog ya maalat",
        "7 ya puto bumbong ya walay keso so nilako",
        "Extra super bibingka, 9 so nilako",
        "Inubos la so puto bumbong",
        "Naubusan kami na ube",
        "2 labat so nankera ya frozen bibingka",
        "Anggapo lay bibingcute ya ham and cheese",
        "Asingger lan maubos so Overload",
        "Antoy target tayo natan ya agew?",
        "Pigay la so nilako tayo?",
        "Maabig ya kabuasan!",
        "Salamat, Mia",
        "Ma-late ak nabuas",
        "Inalok ko na puto bumbong so kada sakey ya angalaw na bibingka",
        "Inmirmir ak tan inbati ko so amin ya sinmabi",
        "Insuheri ko so kahon ya apat imbes ya sakey labat ya piraso",
        "Sueldo kasi kanian ya dakel so too",
        "Walay misa ed simbaan ya asingger kanian ya dinmakel so too kayari",
        "Walay opisina ya nan-order na 20 ya kahon para ed party da",
        "Walay sakey ya customer ya angalaw na 15 ya piraso para ed reunion na pamilya",
        "Mauran kanian ya labay na saray too so mapetang",
        "Mabetbet so panaon natan, bagay ed bibingka",
        "Ag ko amta, swerte labat ompan",
    ],
}

# Cover and absence messages for the switch cases. en is from the plan; the other five are
# machine drafts by Claude, not checked by native speakers (D18).
COVER = {
    "en": [
        "Who can cover my shift on Saturday?",
        "I'm sick and can't open the shop tomorrow",
        "Can Ana take the afternoon shift?",
        "What time do I start tomorrow?",
        "I'll be 30 minutes late today",
    ],
    "fil": [
        "Sino ang puwedeng pumalit sa shift ko sa Sabado?",
        "May sakit ako at hindi ko mabubuksan ang tindahan bukas",
        "Puwede bang si Ana ang kumuha ng shift sa hapon?",
        "Anong oras ang pasok ko bukas?",
        "Male-late ako ng 30 minuto ngayon",
    ],
    "ceb": [
        "Kinsa may maka-cover sa akong shift sa Sabado?",
        "Masakiton ko ug dili nako maablihan ang tindahan ugma",
        "Pwede ba si Ana mokuha sa shift sa hapon?",
        "Unsang orasa ko mosulod ugma?",
        "Ma-late ko og 30 minutos karon",
    ],
    "hil": [
        "Sin-o ang pwede mag-cover sang akon shift sa Sabado?",
        "May sakit ako kag indi ko mabuksan ang tindahan buwas",
        "Pwede bala si Ana magkuha sang shift sa hapon?",
        "Ano nga oras ang sulod ko buwas?",
        "Ma-late ako sang 30 minutos subong",
    ],
    "war": [
        "Hin-o an pwede mag-cover han akon shift ha Sabado?",
        "May sakit ako ngan diri ko mabubuksan an tindahan buwas",
        "Pwede ba hi Ana magkuha han shift ha hapon?",
        "Ano nga oras an sulod ko buwas?",
        "Ma-late ako hin 30 minutos yana",
    ],
    "bcl": [
        "Siisay an pwedeng mag-cover kan shift ko sa Sabado?",
        "May helang ako asin dai ko mabubukasan an tindahan sa aga",
        "Pwede daw si Ana an magkua kan shift sa hapon?",
        "Anong oras an pasok ko sa aga?",
        "Ma-late ako nin 30 minutos ngonyan",
    ],
}
WHY_ASKED = "You beat today's target! Why do you think sales went well?"
INTENTS = Path(__file__).with_name("intents.jsonl")


def _intent_cases() -> list[Case]:
    """The shift supervisor and conversation rows of the intent test split."""
    cases = []
    for line in INTENTS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["split"] != "test":
            continue
        if row["intent"].startswith("shift_supervisor."):
            cases.append(Case(row["lang"], row["text"], "shift_supervisor"))
        elif row["intent"].startswith("conversation."):
            cases.append(Case(row["lang"], row["text"], "any"))
    return cases


def _spike_case(
    lang: str, label: tuple[str, str | None, str | None, str | None], text: str
) -> Case:
    """One spike message with the agent its label maps to."""
    key, kind = label[0], label[1]
    if key.startswith("W"):
        return Case(lang, text, "sales_supervisor", "sales_supervisor", WHY_ASKED, "follow_up")
    if key == "Q5":
        return Case(lang, text, "shift_supervisor")
    if key in ("Q3", "Q4"):
        return Case(lang, text, "any")
    agent = "inventory_manager" if kind == "stock" else "sales_supervisor"
    return Case(lang, text, agent)


def _switch_cases() -> list[Case]:
    """Five sales messages while the shift supervisor is active, five cover messages while the
    sales supervisor is, per language."""
    cases = []
    for lang, cover in COVER.items():
        sales = TEXTS[lang][:5]
        cases += [
            Case(lang, t, "sales_supervisor", "shift_supervisor", group="switch") for t in sales
        ]
        cases += [
            Case(lang, t, "shift_supervisor", "sales_supervisor", group="switch") for t in cover
        ]
    return cases


CASES: list[Case] = [
    *_intent_cases(),
    *(
        _spike_case(lang, lab, txt)
        for lang, texts in TEXTS.items()
        for lab, txt in zip(LABELS, texts, strict=True)
    ),
    *_switch_cases(),
]
