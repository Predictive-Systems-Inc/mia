"""The hr officer decider eval set (spec 2026-10-19-hr-officer, sections 4 and 10): what
Ferino's clerks, head staff and owner send, ten messages per scenario in each gated language,
split into halves by seed (even seeds tune, odd seeds gate; a seed's languages share a half, so
no text is in both). Data only; test_hr_officer_evals.py runs it.

Synthetic, written by Claude, not native speakers (D18). English seeds come first; the five
Philippine languages are drafts for a clerk texting on a phone, and Q28 to Q35 cover their
review. Dates are written as clerks write them ("next week Monday", "sa susunod na linggo
Lunes", "Dec 25", "bukas"); the run pins today to TODAY, a Monday, so weekday phrases are stable
and Christmas is inside the fourteen days a holiday question picks from. find_dates reads no
"tomorrow" or "today" word in hil, war or bcl and no "next week" there or in ceb, so those
leave messages name the weekday or the date (the shape test checks every leave date is a
candidate). Expected inputs are offsets from TODAY ("+7d"), resolved by on().

The short half (SHORT, D42): twelve en and twelve fil messages as clerks and the owner type on a
phone (lowercase, no punctuation, digits, one to six words), the en and fil written apart, not
translations; two per language are ambiguous and should ask ("ask"). Its one rule is no wrong
write (gate.wrong_writes); its expected slots are reported, never a bar. Its dates were written
for a Tuesday in November (PP_TODAY): "dec 2" and "nov 30" are past on this TODAY."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str
    role: str  # a role of a seeded Ferino's person (clerk Ana, supervisor Marites, owner Rosa)
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "gate", "short"] = "tune"
    # file_leave {"start", "end"} and holiday_pay {"day"} as offsets; contributions {"which"}
    expected_slots: dict[str, str] = field(default_factory=dict)


GATED_LANGS = ("en", "fil", "ceb", "hil", "war", "bcl")
TODAY = dt.date(2026, 12, 14)  # a Monday


def on(value: str) -> str:
    """An offset "+Nd" as the ISO date N days after TODAY; any other value as it is."""
    if value.startswith("+") and value.endswith("d"):
        return (TODAY + dt.timedelta(days=int(value[1:-1]))).isoformat()
    return value


Row = tuple[dict[str, str], str, str, str, str, str, str]  # slots, then en fil ceb hil war bcl
NONE: dict[str, str] = {}

MY_HOURS: list[Row] = [
    (NONE, "how many hours did I work this cutoff", "ilang oras na ang trabaho ko ngayong cutoff",
     "pila na ka oras akong trabaho ani nga cutoff", "pila na ka oras ang obra ko sini nga cutoff",
     "pira na ka oras an akon trabaho hini nga cutoff", "pira na an oras kan trabaho ko sa cutoff na ini"),
    (NONE, "hours ko last cutoff?", "ilang oras ko noong nakaraang cutoff?",
     "pila akong oras sa miaging cutoff?", "pila ang oras ko sang nagligad nga cutoff?",
     "pira an akon oras han nakaagi nga cutoff?", "pira an oras ko kan nakaaging cutoff?"),
    (NONE, "how many hours have I worked this month", "ilang oras na ako nagtrabaho ngayong buwan",
     "pila na ka oras ko nagtrabaho karong bulana", "pila na ka oras ako nag-obra subong nga bulan",
     "pira na ka oras ako nagtrabaho yana nga bulan", "pira na an oras na nagtrabaho ako ngunyan na bulan"),
    (NONE, "did I have overtime last cutoff?", "may overtime ba ako noong nakaraang cutoff?",
     "naa ba koy overtime sa miaging cutoff?", "may overtime bala ako sang nagligad nga cutoff?",
     "may-ada ba ako overtime han nakaagi nga cutoff?", "igwa daw akong overtime kan nakaaging cutoff?"),
    (NONE, "total hours ko this cutoff please", "pakitingnan ang kabuuang oras ko ngayong cutoff",
     "palihug tan-awa ang total nakong oras ani nga cutoff", "palihog tan-awa ang total sang oras ko sini nga cutoff",
     "alayon kitaa an total han akon oras hini nga cutoff", "paki-hiling an total kan oras ko ngunyan na cutoff"),
    (NONE, "how many hours last month", "ilang oras ako noong isang buwan",
     "pila ka oras ko sa miaging bulan", "pila ka oras ako sang nagligad nga bulan",
     "pira ka oras ako han nakaagi nga bulan", "pira an oras ko kan nakaaging bulan"),
    (NONE, "check my timesheet for this cutoff", "pakicheck ng timesheet ko ngayong cutoff",
     "palihug check sa akong timesheet ani nga cutoff", "palihog check sang timesheet ko sini nga cutoff",
     "alayon check han akon timesheet hini nga cutoff", "paki-check an timesheet ko sa cutoff na ini"),
    (NONE, "how much overtime do I have this month", "ilang oras ang overtime ko ngayong buwan",
     "pila na akong overtime karong bulana", "pila na ang overtime ko subong nga bulan",
     "pira na an akon overtime yana nga bulan", "pira na an overtime ko ngunyan na bulan"),
    (NONE, "how many hours did I work this cutoff, I covered two shifts",
     "ilang oras ako ngayong cutoff, nag-cover ako ng dalawang shift",
     "pila ka oras ko ani nga cutoff, nag-cover ko og duha ka shift",
     "pila ka oras ako sini nga cutoff, nag-cover ako sang duha ka shift",
     "pira ka oras ako hini nga cutoff, nag-cover ako hin duha nga shift",
     "pira an oras ko sa cutoff na ini, nag-cover ako nin duwang shift"),
    (NONE, "my total hours last payroll?", "kabuuang oras ko noong huling payroll?",
     "total nakong oras sa miaging payroll?", "total sang oras ko sang nagligad nga payroll?",
     "total han akon oras han nakaagi nga payroll?", "total kan oras ko kan nakaaging payroll?"),
]  # fmt: skip

PAYDAY: list[Row] = [
    (NONE, "when is payday", "kailan ang sahod", "kanus-a ang sweldo", "san-o ang sweldo",
     "san-o an sweldo", "nuarin an sweldo"),
    (NONE, "when do we get paid", "kailan tayo babayaran", "kanus-a ta bayran",
     "san-o kita bayaran", "san-o kita bayaran hit sweldo", "nuarin kita babayadan"),
    (NONE, "when's the next sweldo", "kailan ang susunod na sweldo", "kanus-a ang sunod nga sweldo",
     "san-o ang masunod nga sweldo", "san-o an sunod nga sweldo", "nuarin an sunod na sweldo"),
    (NONE, "what day is our salary", "anong araw ang sahod natin", "unsang adlawa ang atong sweldo",
     "ano nga adlaw ang aton sweldo", "ano nga adlaw an aton sweldo", "anong aldaw an satong sweldo"),
    (NONE, "is payday this week?", "sahod na ba ngayong linggo?", "sweldo na ba ani nga semana?",
     "sweldo na bala sini nga semana?", "sweldo na ba hini nga semana?", "sweldo na daw ngunyan na semana?"),
    (NONE, "when will the pay come in", "kailan papasok ang sahod", "kanus-a mosulod ang sweldo",
     "san-o masulod ang sweldo", "san-o masulod an sweldo", "nuarin malaog an sweldo"),
    (NONE, "next payday when?", "kailan ang susunod na payday?", "kanus-a ang sunod payday?",
     "san-o ang masunod nga payday?", "san-o an sunod nga payday?", "nuarin an sunod na payday?"),
    (NONE, "payday na ba?", "sahod na ba?", "sweldo na ba?", "sweldo na bala?",
     "sweldo na ba yana?", "sweldo na daw?"),
    (NONE, "when is the next payout", "kailan ang susunod na bigayan ng sahod",
     "kanus-a ang sunod nga hatag sa sweldo", "san-o ang masunod nga hatag sang sweldo",
     "san-o an sunod nga hatag han sweldo", "nuarin an sunod na tao kan sweldo"),
    (NONE, "what date is the salary", "anong petsa ang sahod", "unsang petsa ang sweldo",
     "ano nga petsa ang sweldo", "ano nga petsa an sweldo", "anong petsa an sweldo"),
]  # fmt: skip

THIRTEENTH: list[Row] = [
    (NONE, "how much is my 13th month", "magkano ang 13th month ko", "pila akong 13th month",
     "pila ang 13th month ko", "pira an akon 13th month", "magkano an 13th month ko"),
    (NONE, "when is the 13th month pay released", "kailan ilalabas ang 13th month pay",
     "kanus-a i-release ang 13th month pay", "san-o i-release ang 13th month pay",
     "san-o igbibigay an 13th month pay", "nuarin ipapagawas an 13th month pay"),
    (NONE, "13th month ko how much so far", "13th month ko magkano na", "13th month nako pila na",
     "13th month ko pila na subong", "13th month ko pira na", "13th month ko magkano na ngunyan"),
    (NONE, "will we get 13th month this December", "may 13th month ba tayo ngayong Disyembre",
     "naa ba tay 13th month karong Disyembre", "may 13th month bala kita subong nga Disyembre",
     "may-ada ba kita 13th month yana nga Disyembre", "igwa daw kitang 13th month ngunyan na Disyembre"),
    (NONE, "how much 13th month do I have so far", "magkano na ang naipon kong 13th month",
     "pila na ang natigom nakong 13th month", "pila na ang natipon ko nga 13th month",
     "pira na an natipon ko nga 13th month", "magkano na an natipon kong 13th month"),
    (NONE, "when do we receive the 13th month", "kailan natin matatanggap ang 13th month",
     "kanus-a nato madawat ang 13th month", "san-o naton mabaton ang 13th month",
     "san-o naton mababaton an 13th month", "nuarin ta maaako an 13th month"),
    (NONE, "computation of my 13th month pay", "kwenta ng 13th month pay ko",
     "kwenta sa akong 13th month pay", "kwenta sang 13th month pay ko",
     "kwenta han akon 13th month pay", "kwenta kan 13th month pay ko"),
    (NONE, "is the 13th month given before Christmas", "ibibigay ba ang 13th month bago mag-Pasko",
     "ihatag ba ang 13th month sa dili pa Pasko", "ihatag bala ang 13th month antes sang Paskwa",
     "igbibigay ba an 13th month antes han Pasko", "itatao daw an 13th month bago an Pasko"),
    (NONE, "13th month pay amount please", "pakisabi ang halaga ng 13th month pay ko",
     "palihug ingna pila akong 13th month pay", "palihog sugiri pila ang 13th month pay ko",
     "alayon sumati pira an akon 13th month pay", "paki-sabi kun magkano an 13th month pay ko"),
    (NONE, "when is the 13th month", "kailan ang 13th month", "kanus-a ang 13th month",
     "san-o ang 13th month", "san-o an 13th month", "nuarin an 13th month"),
]  # fmt: skip

SSS, PH, PI, ALL = ({"which": w} for w in ("sss", "philhealth", "pagibig", "all"))
CONTRIBUTIONS: list[Row] = [
    (SSS, "how much was my SSS this payroll?", "magkano ang SSS ko ngayong payroll?",
     "pila akong SSS ani nga payroll?", "pila ang SSS ko sini nga payroll?",
     "pira an akon SSS hini nga payroll?", "magkano an SSS ko sa payroll na ini?"),
    (PH, "how much is my PhilHealth", "magkano ang PhilHealth ko", "pila akong PhilHealth",
     "pila ang PhilHealth ko", "pira an akon PhilHealth", "magkano an PhilHealth ko"),
    (PI, "was my Pag-IBIG deducted?", "nakaltasan ba ako ng Pag-IBIG?",
     "gikaltasan ba ko sa Pag-IBIG?", "ginbawasan bala ako sang Pag-IBIG?",
     "ginkaltasan ba ako han Pag-IBIG?", "binawasan daw ako nin Pag-IBIG?"),
    (ALL, "what were my contributions, SSS PhilHealth and Pag-IBIG?",
     "ano ang mga kaltas ko sa SSS, PhilHealth at Pag-IBIG?",
     "unsa akong mga kaltas sa SSS, PhilHealth ug Pag-IBIG?",
     "ano ang mga bawas ko sa SSS, PhilHealth kag Pag-IBIG?",
     "ano an akon mga kaltas ha SSS, PhilHealth ngan Pag-IBIG?",
     "ano an mga bawas ko sa SSS, PhilHealth asin Pag-IBIG?"),
    (SSS, "is my SSS paid?", "bayad na ba ang SSS ko?", "bayad na ba akong SSS?",
     "bayad na bala ang SSS ko?", "bayad na ba an akon SSS?", "bayad na daw an SSS ko?"),
    (PI, "how much hulog for pag ibig last sahod", "magkano ang hulog sa pag ibig noong huling sahod",
     "pila ang hulog sa pag ibig sa miaging sweldo", "pila ang hulog sa pag ibig sang nagligad nga sweldo",
     "pira an hulog ha pag ibig han nakaagi nga sweldo", "magkano an hulog sa pag ibig kan nakaaging sweldo"),
    (PH, "how much PhilHealth did they take from my pay", "magkano ang kinaltas na PhilHealth sa sahod ko",
     "pila ang gikaltas nga PhilHealth sa akong sweldo", "pila ang ginbawas nga PhilHealth sa sweldo ko",
     "pira an ginkaltas nga PhilHealth ha akon sweldo", "magkano an binawas na PhilHealth sa sweldo ko"),
    (ALL, "my contributions last cutoff", "mga kontribusyon ko noong nakaraang cutoff",
     "akong mga kontribusyon sa miaging cutoff", "mga kontribusyon ko sang nagligad nga cutoff",
     "akon mga kontribusyon han nakaagi nga cutoff", "mga kontribusyon ko kan nakaaging cutoff"),
    (SSS, "SSS contribution how much", "magkano ang hulog ko sa SSS", "pila akong hulog sa SSS",
     "pila ang hulog ko sa SSS", "pira an akon hulog ha SSS", "magkano an hulog ko sa SSS"),
    (PI, "how much is my Pagibig share", "magkano ang share ko sa Pagibig",
     "pila akong share sa Pagibig", "pila ang share ko sa Pagibig",
     "pira an akon share ha Pagibig", "magkano an share ko sa Pagibig"),
]  # fmt: skip


def _leave(start: int, end: int) -> dict[str, str]:
    return {"start": f"+{start}d", "end": f"+{end}d"}


FILE_LEAVE: list[Row] = [
    (_leave(7, 9), "I want to file leave next week Monday to Wednesday",
     "Gusto ko mag-file ng leave sa susunod na linggo Lunes hanggang Miyerkules",
     "Mag-file ko og leave sunod semana, Lunes hangtod Miyerkules",
     "Magfile ako leave sa masunod nga semana, Lunes tubtob Miyerkules",
     "Mag-file ako hin leave ha sunod nga semana, Lunes tubtob Miyerkules",
     "Mag-file ako nin leave sa sunod na semana, Lunes sagkod Miyerkules"),
    (_leave(0, 0), "sick today, I can't come in", "May sakit ako ngayon, hindi ako makakapasok",
     "Masakiton ko karon, dili ko makasulod", "Masakit ako subong, Dec 14, indi ako makasulod",
     "Masakit ako yana, Dec 14, diri ako makakasulod", "May helang ako ngunyan, Dec 14, dai ako makakalaog"),
    (_leave(4, 4), "Can I take leave on Friday?", "Pwede ba ako mag-leave sa Biyernes?",
     "Pwede ko mo-leave sa Biyernes?", "Pwede ako mag-leave sa Biyernes?",
     "Pwede ba ako mag-leave ha Biyernes?", "Pwede daw ako mag-leave sa Biyernes?"),
    (_leave(1, 1), "leave tomorrow please, family errand", "leave po ako bukas, may lakad ang pamilya",
     "leave ko ugma palihug, naa mi lakaw sa pamilya", "leave ako sa Martes, may lakat ang pamilya",
     "leave ako ha Martes, may-ada lakat an pamilya", "leave ako sa Martes, may lakaw an pamilya"),
    (_leave(7, 9), "file VL Dec 21 to Dec 23", "pa-file ng VL Dec 21 hanggang Dec 23",
     "pa-file og VL Dec 21 hangtod Dec 23", "pa-file VL Dec 21 tubtob Dec 23",
     "pa-file hin VL Dec 21 tubtob Dec 23", "pa-file nin VL Dec 21 sagkod Dec 23"),
    (_leave(1, 1), "I'm sick, I won't come in tomorrow", "Masama pakiramdam ko, hindi ako papasok bukas",
     "Masakiton ko, dili ko musulod ugma", "Masakit ako, indi ako makasulod sa Martes",
     "Masakit ako, diri ako makakasulod ha Martes", "May helang ako, dai ako makakalaog sa Martes"),
    (_leave(3, 3), "I'll be absent on Thursday, I have an appointment",
     "Absent ako sa Huwebes, may lakad ako", "Absent ko sa Huwebes, naa koy lakaw",
     "Absent ako sa Huwebes, may lakat ako", "Absent ako ha Huwebes, may-ada ako lakat",
     "Absent ako sa Huwebes, may lakaw ako"),
    (_leave(14, 16), "leave from Dec 28 to Dec 30 please, going home to the province",
     "leave ako Dec 28 hanggang Dec 30, uuwi ako ng probinsya",
     "leave ko Dec 28 hangtod Dec 30, mopauli ko sa probinsya",
     "leave ako Dec 28 tubtob Dec 30, mapauli ako sa probinsya",
     "leave ako Dec 28 tubtob Dec 30, mauli ako ha probinsya",
     "leave ako Dec 28 sagkod Dec 30, mauli ako sa probinsya"),
    (_leave(1, 2), "Can I rest on Tuesday and Wednesday?",
     "Pwede ba akong mag-day off sa Martes at Miyerkules?",
     "Pwede ko mopahulay sa Martes ug Miyerkules?", "Pwede ako magpahuway sa Martes kag Miyerkules?",
     "Pwede ba ako magpahuway ha Martes ngan Miyerkules?",
     "Pwede daw ako magpahingalo sa Martes asin Miyerkules?"),
    (_leave(8, 8), "please file a leave for me next week Tuesday",
     "paki-file ng leave ko sa susunod na linggo Martes", "palihug i-file akong leave sa Dec 22",
     "palihog i-file ang leave ko sa Dec 22", "alayon i-file an akon leave ha Dec 22",
     "paki-file an leave ko sa Dec 22"),
]  # fmt: skip

LEAVE_BALANCE: list[Row] = [
    (NONE, "how many leave days do I have left", "ilang araw pa ang natitirang leave ko",
     "pila pa ka adlaw ang nabilin nakong leave", "pila pa ka adlaw ang nabilin nga leave ko",
     "pira pa ka adlaw an nabilin nga akon leave", "pira pang aldaw an natadang leave ko"),
    (NONE, "ilang leave pa ako?", "ilang leave pa ba ang meron ako?", "pila pa akong leave?",
     "pila pa ang leave ko?", "pira pa an akon leave?", "pira pa an leave ko?"),
    (NONE, "my remaining sick leave", "natitirang sick leave ko", "nabilin nakong sick leave",
     "nabilin ko nga sick leave", "nabilin nga akon sick leave", "natadang sick leave ko"),
    (NONE, "do I still have vacation leave", "may vacation leave pa ba ako",
     "naa pa ba koy vacation leave", "may vacation leave pa bala ako",
     "may-ada pa ba ako vacation leave", "igwa pa daw akong vacation leave"),
    (NONE, "leave balance please", "pakitingnan ang leave balance ko", "palihug ang akong leave balance",
     "palihog ang leave balance ko", "alayon an akon leave balance", "paki-hiling an leave balance ko"),
    (NONE, "how many SIL do I have", "ilan ang SIL ko", "pila akong SIL", "pila ang SIL ko",
     "pira an akon SIL", "pira an SIL ko"),
    (NONE, "how many days off can I still take", "ilang araw pa ako pwedeng mag-leave",
     "pila pa ka adlaw ko pwede mo-leave", "pila pa ka adlaw ako pwede mag-leave",
     "pira pa ka adlaw ako pwede mag-leave", "pira pang aldaw ako pwedeng mag-leave"),
    (NONE, "how much leave is left for this year", "ilan pa ang natitirang leave ngayong taon",
     "pila pa ang nabilin nga leave karong tuiga", "pila pa ang nabilin nga leave subong nga tuig",
     "pira pa an nabilin nga leave yana nga tuig", "pira pa an natadang leave ngunyan na taon"),
    (NONE, "do I have leave credits", "may leave credits ba ako", "naa ba koy leave credits",
     "may leave credits bala ako", "may-ada ba ako leave credits", "igwa daw akong leave credits"),
    (NONE, "check my leave balance", "pakicheck ng leave balance ko", "palihug check sa akong leave balance",
     "palihog check sang leave balance ko", "alayon check han akon leave balance",
     "paki-check an leave balance ko"),
]  # fmt: skip


def _day(n: int) -> dict[str, str]:
    return {"day": f"+{n}d"}


HOLIDAY_PAY: list[Row] = [
    (_day(11), "do we get holiday pay on Dec 25?", "may holiday pay ba tayo sa Dec 25?",
     "naa ba tay holiday pay sa Dec 25?", "may holiday pay bala kita sa Dec 25?",
     "may-ada ba kita holiday pay ha Dec 25?", "igwa daw kitang holiday pay sa Dec 25?"),
    (_day(1), "is tomorrow a holiday?", "holiday ba bukas?", "holiday ba ugma?",
     "holiday bala buwas?", "holiday ba buwas?", "holiday daw sa aga?"),
    (_day(11), "what's the pay if I work on Christmas?", "magkano ang bayad kung papasok ako sa Pasko?",
     "pila ang bayad kung mosulod ko sa Pasko?", "pila ang bayad kon magsulod ako sa Paskwa?",
     "pira an bayad kun masulod ako ha Pasko?", "magkano an bayad kun malaog ako sa Pasko?"),
    (_day(10), "is Dec 24 a holiday? double pay?", "holiday ba ang Dec 24? doble ba ang bayad?",
     "holiday ba ang Dec 24? doble ba ang bayad?", "holiday bala ang Dec 24? doble bala ang bayad?",
     "holiday ba an Dec 24? doble ba an bayad?", "holiday daw an Dec 24? doble daw an bayad?"),
    (_day(10), "Christmas Eve, is that a holiday?", "Bisperas ng Pasko, holiday ba yun?",
     "Bisperas sa Pasko, holiday ba na?", "Bisperas sang Paskwa, holiday bala ina?",
     "Bisperas han Pasko, holiday ba iton?", "Bisperas kan Pasko, holiday daw iyan?"),
    (_day(3), "is Thursday a holiday?", "holiday ba sa Huwebes?", "holiday ba sa Huwebes?",
     "holiday bala sa Huwebes?", "holiday ba ha Huwebes?", "holiday daw sa Huwebes?"),
    (_day(11), "if I work Dec 25 how much is the rate", "kung pumasok ako sa Dec 25 magkano ang rate",
     "kung mosulod ko sa Dec 25 pila ang rate", "kon magsulod ako sa Dec 25 pila ang rate",
     "kun masulod ako ha Dec 25 pira an rate", "kun malaog ako sa Dec 25 magkano an rate"),
    (_day(4), "holiday pay on Friday?", "may holiday pay ba sa Biyernes?",
     "naa bay holiday pay sa Biyernes?", "may holiday pay bala sa Biyernes?",
     "may-ada ba holiday pay ha Biyernes?", "igwa daw holiday pay sa Biyernes?"),
    (_day(11), "is next week Friday a holiday?", "holiday ba sa susunod na linggo Biyernes?",
     "holiday ba ang Biyernes sa sunod semana?", "holiday bala ang Biyernes sa masunod nga semana?",
     "holiday ba an Biyernes ha sunod nga semana?", "holiday daw an Biyernes sa sunod na semana?"),
    (_day(12), "is Dec 26 a holiday or a regular day?", "holiday ba ang Dec 26 o regular na araw?",
     "holiday ba ang Dec 26 o regular nga adlaw?", "holiday bala ang Dec 26 ukon regular nga adlaw?",
     "holiday ba an Dec 26 o regular nga adlaw?", "holiday daw an Dec 26 o regular na aldaw?"),
]  # fmt: skip

MY_PAYSLIP: list[Row] = [
    (NONE, "my payslip is missing", "nawawala ang payslip ko", "nawala akong payslip",
     "nadula ang payslip ko", "nawara an akon payslip", "nawara an payslip ko"),
    (NONE, "send my payslip", "ipadala ang payslip ko", "ipadala akong payslip",
     "ipadala ang payslip ko", "ipadara an akon payslip", "ipadara an payslip ko"),
    (NONE, "can I get my payslip again", "pwede ko bang makuha ulit ang payslip ko",
     "pwede nako makuha balik akong payslip", "pwede ko makuha liwat ang payslip ko",
     "pwede ko makuha utro an akon payslip", "pwede ko daw makua giraray an payslip ko"),
    (NONE, "I didn't receive my pay slip", "hindi ko natanggap ang pay slip ko",
     "wala nako nadawat akong pay slip", "wala ko nabaton ang pay slip ko",
     "waray ko nakarawat an akon pay slip", "dai ko naako an pay slip ko"),
    (NONE, "resend payslip please", "pakipadala ulit ng payslip", "palihug ipadala balik ang payslip",
     "palihog ipadala liwat ang payslip", "alayon ipadara utro an payslip",
     "paki-padara giraray an payslip"),
    (NONE, "where is my payslip for the last payroll", "nasaan ang payslip ko sa huling payroll",
     "asa akong payslip sa miaging payroll", "diin ang payslip ko sang nagligad nga payroll",
     "hain an akon payslip han nakaagi nga payroll", "hain an payslip ko kan nakaaging payroll"),
    (NONE, "send the payslip again to me", "pa send ulit ng payslip ko", "pa send balik sa akong payslip",
     "pa send liwat sang payslip ko", "pa send utro han akon payslip", "pa send giraray kan payslip ko"),
    (NONE, "lost my payslip, send again", "nawala ko ang payslip, pakipadala ulit",
     "nawala nako ang payslip, ipadala balik", "nadula ko ang payslip, ipadala liwat",
     "nawara ko an payslip, ipadara utro", "nawara ko an payslip, ipadara giraray"),
    (NONE, "I need a copy of my payslip", "kailangan ko ng kopya ng payslip ko",
     "kinahanglan nako og kopya sa akong payslip", "kinahanglan ko sang kopya sang payslip ko",
     "kinahanglan ko hin kopya han akon payslip", "kaipuhan ko nin kopya kan payslip ko"),
    (NONE, "payslip please", "payslip po", "payslip palihug", "payslip palihog",
     "payslip alayon", "payslip tabi"),
]  # fmt: skip

CERTIFICATE: list[Row] = [
    (NONE, "COE for Ana", "COE para kay Ana", "COE para ni Ana", "COE para kay Ana",
     "COE para kan Ana", "COE para ki Ana"),
    (NONE, "make a certificate of employment for Liza", "gawan mo ng certificate of employment si Liza",
     "himoi og certificate of employment si Liza", "himui sang certificate of employment si Liza",
     "himoa hin certificate of employment hi Liza", "gibuhan nin certificate of employment si Liza"),
    (NONE, "I need a COE for Marites", "kailangan ko ng COE para kay Marites",
     "kinahanglan nako og COE para ni Marites", "kinahanglan ko sang COE para kay Marites",
     "kinahanglan ko hin COE para kan Marites", "kaipuhan ko nin COE para ki Marites"),
    (NONE, "certificate of employment for Ana please, she needs it for a loan",
     "certificate of employment para kay Ana, kailangan niya sa loan",
     "certificate of employment para ni Ana, kinahanglan niya sa loan",
     "certificate of employment para kay Ana, kinahanglan niya sa loan",
     "certificate of employment para kan Ana, kinahanglan niya ha loan",
     "certificate of employment para ki Ana, kaipuhan niya sa loan"),
    (NONE, "prepare a COE for Liza", "ihanda ang COE ni Liza", "andama ang COE ni Liza",
     "preparahon ang COE ni Liza", "andama an COE ni Liza", "andamon an COE ni Liza"),
    (NONE, "employment certificate for Marites", "employment certificate ni Marites",
     "employment certificate ni Marites palihug", "employment certificate ni Marites palihog",
     "employment certificate ni Marites alayon", "employment certificate ni Marites tabi"),
    (NONE, "Ana is asking for a COE", "humihingi si Ana ng COE", "nangayo si Ana og COE",
     "nagapangayo si Ana sang COE", "nangangayo hi Ana hin COE", "naghahagad si Ana nin COE"),
    (NONE, "COE Liza", "COE ni Liza po", "COE ni Liza", "COE ni Liza bala",
     "COE ni Liza ba", "COE ni Liza daw"),
    (NONE, "please draft a certificate of employment for Ana",
     "pakigawa ng certificate of employment ni Ana", "palihug himo og certificate of employment ni Ana",
     "palihog himo sang certificate of employment ni Ana", "alayon paghimo hin certificate of employment ni Ana",
     "paki-gibo nin certificate of employment ni Ana"),
    (NONE, "can you make Marites's COE", "pwede mo bang gawin ang COE ni Marites",
     "pwede nimo himoon ang COE ni Marites", "pwede mo himuon ang COE ni Marites",
     "pwede mo himoon an COE ni Marites", "pwede mo daw gibohon an COE ni Marites"),
]  # fmt: skip

REPLY_ONLY: list[Row] = [
    (NONE, "good morning", "magandang umaga", "maayong buntag", "maayong aga",
     "maupay nga aga", "marhay na aga"),
    (NONE, "thanks", "salamat", "salamat kaayo", "salamat gid", "salamat", "salamat tabi"),
    (NONE, "hi Mia", "hi Mia po", "hi Mia, kumusta", "hi Mia, kamusta", "hi Mia, kumusta ka",
     "hi Mia, kumusta ka tabi"),
    (NONE, "thank you so much", "maraming salamat po", "daghang salamat", "madamo gid nga salamat",
     "damo nga salamat", "dakulang salamat"),
    (NONE, "hello", "hello po", "hello diha", "hello dira", "hello dida", "hello digdi"),
    (NONE, "ok thanks", "ok salamat", "ok salamat ha", "sige salamat", "sige salamat ha", "sige salamat"),
    (NONE, "good afternoon", "magandang hapon", "maayong hapon", "maayong hapon sa inyo",
     "maupay nga kulop", "marhay na hapon"),
    (NONE, "thanks a lot Mia", "salamat nang marami Mia", "salamat kaayo Mia", "salamat gid Mia",
     "salamat hin damo Mia", "salamat nin marhay Mia"),
    (NONE, "hey", "uy", "uy, hi", "oy, hi", "oy", "oy, hi tabi"),
    (NONE, "thanks Mia", "salamat Mia", "salamat Mia ha", "salamat Mia ah",
     "salamat Mia ha imo", "salamat sa saimo Mia"),
]  # fmt: skip

SEEDS: dict[str, list[Row]] = {
    "my_hours": MY_HOURS,
    "payday": PAYDAY,
    "thirteenth": THIRTEENTH,
    "contributions": CONTRIBUTIONS,
    "file_leave": FILE_LEAVE,
    "leave_balance": LEAVE_BALANCE,
    "holiday_pay": HOLIDAY_PAY,
    "my_payslip": MY_PAYSLIP,
    "certificate": CERTIFICATE,
    "reply_only": REPLY_ONLY,
}
SCENARIOS = tuple(SEEDS)


def _role(scenario: str, seed: int) -> str:
    """Rosa asks the certificates; Marites asks the last two hours questions; Ana the rest."""
    if scenario == "certificate":
        return "owner"
    return "supervisor" if scenario == "my_hours" and seed >= 8 else "clerk"


ASK = "ask"
# The short half (D42): (language, sender role, text, expected action or "ask", slots)
SHORT: list[tuple[str, str, str, str, dict[str, str]]] = [
    ("en", "clerk", "my hrs this cutoff", "my_hours", NONE),
    ("en", "clerk", "when payday", "payday", NONE),
    ("en", "clerk", "13th month how much", "thirteenth", NONE),
    ("en", "clerk", "sss deduction last pay", "contributions", NONE),
    ("en", "clerk", "vl dec 2 to 3", "file_leave", {"start": "2026-12-02"}),
    ("en", "clerk", "sick leave tmrw pls", "file_leave", {"start": "+1d"}),
    ("en", "clerk", "leave left", "leave_balance", NONE),
    ("en", "clerk", "holiday pay nov 30", "holiday_pay", {"day": "2026-11-30"}),
    ("en", "clerk", "resend payslip pls", "my_payslip", NONE),
    ("en", "owner", "need coe ana", "certificate", NONE),
    ("en", "clerk", "cutoff", ASK, NONE),
    ("en", "clerk", "nov 30", ASK, {"day": "2026-11-30"}),
    ("fil", "clerk", "ilang oras ko ngayong cutoff", "my_hours", NONE),
    ("fil", "clerk", "kelan sweldo natin", "payday", NONE),
    ("fil", "clerk", "magkano 13th month ko", "thirteenth", NONE),
    ("fil", "clerk", "philhealth kaltas ko", "contributions", NONE),
    ("fil", "clerk", "pa file vl biyernes", "file_leave", {"start": "+4d"}),
    ("fil", "clerk", "day off ako sab pls", "file_leave", {"start": "+5d"}),
    ("fil", "clerk", "ilan pa leave ko", "leave_balance", NONE),
    ("fil", "clerk", "holiday ba lunes", "holiday_pay", {"day": "+7d"}),
    ("fil", "clerk", "payslip ko po ulit", "my_payslip", NONE),
    ("fil", "owner", "pa coe kay liza", "certificate", NONE),
    ("fil", "clerk", "sahod", ASK, NONE),
    ("fil", "clerk", "leave po", ASK, NONE),
]

CASES: list[Case] = [
    Case(
        lang=lang,
        scenario=scenario,
        text=text,
        expected_action=scenario,
        role=_role(scenario, i),
        half="tune" if i % 2 == 0 else "gate",
        expected_slots=slots,
    )
    for scenario, rows in SEEDS.items()
    for i, (slots, *texts) in enumerate(rows)
    for lang, text in zip(GATED_LANGS, texts, strict=True)
] + [
    Case(lang, "short", text, action, role, half="short", expected_slots=slots)
    for lang, role, text, action, slots in SHORT
]
