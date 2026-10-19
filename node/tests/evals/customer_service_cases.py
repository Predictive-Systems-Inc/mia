"""The customer service decider eval set (spec 2026-10-19-customer-service, scenarios 1 to 8):
what Ferino's customers (scenarios 1 to 7, the customer side) and its clerks and head staff
(scenario 8, the staff side) send, ten messages per scenario in each gated language, split into
halves by seed (even seeds tune, odd seeds gate; a seed's languages share a half, so no text is
in both). Data only; test_customer_service_evals.py runs it.

Synthetic, written by Claude, not native speakers (D18). English seeds come first; the five
Philippine languages are drafts for a customer or a clerk texting on a phone, and Q28 to Q35
cover their review. The run pins today to TODAY, a Tuesday (the cs fixture seeds Ferino's on
the same day, so Mila's 15:00 pickup is today's one order on the staff side). Orders name their
counts in digits, their time as code reads it (8am, 5:30pm, alas 4) and their day with a word
find_dates reads (bukas, ugma, buwas, sa aga, a weekday, or none for today); the shape test
checks each one parses to the expected lines, time and day."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str
    role: str  # customer (the seeded Mila), or a seeded person's role (clerk, supervisor)
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "gate"] = "tune"
    # place_order only: (item name, quantity) in message order, "HH:MM", a day offset "+Nd"
    expected_lines: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    expected_time: str = ""
    expected_day: str = ""


GATED_LANGS = ("en", "fil", "ceb", "hil", "war", "bcl")
TODAY = dt.date(2026, 10, 20)  # a Tuesday, the cs fixture's day


def on(offset: str) -> str:
    """An offset "+Nd" as the ISO date N days after TODAY."""
    return (TODAY + dt.timedelta(days=int(offset[1:-1]))).isoformat()


Row = tuple[str, str, str, str, str, str]  # en fil ceb hil war bcl

HOURS: list[Row] = [
    ("are you open now?", "open pa ba kayo?", "abri pa mo karon?", "bukas pa kamo subong?",
     "bukas pa kamo yana?", "bukas pa kamo ngunyan?"),
    ("what time do you close tonight?", "anong oras kayo nagsasara mamayang gabi?",
     "unsang orasa mo magsira karong gabii?", "ano oras kamo magsira karon gab-i?",
     "ano nga oras kamo nagsasara yana nga gab-i?", "anong oras kamo nagsasara ngunyan na banggi?"),
    ("what time do you open tomorrow?", "anong oras kayo magbubukas bukas?",
     "unsang orasa mo moabri ugma?", "ano oras kamo magbukas buwas?",
     "ano nga oras kamo magbubukas buwas?", "anong oras kamo mabukas sa aga?"),
    ("are you open on Sunday?", "bukas ba kayo sa Linggo?", "abri ba mo sa Dominggo?",
     "bukas bala kamo sa Domingo?", "bukas ba kamo han Domingo?", "bukas daw kamo sa Domingo?"),
    ("store hours po?", "ano po ang oras ng tindahan ninyo?", "unsa inyong oras sa tindahan?",
     "ano ang oras sang tindahan ninyo?", "ano an oras han tindahan niyo?",
     "ano an oras kan tindahan nindo?"),
    ("still open? I'm on my way", "bukas pa po ba? papunta na ako", "abri pa ba? padulong na ko",
     "bukas pa bala? pakadto na ako", "bukas pa ba? papakadto na ako",
     "bukas pa daw? papasiring na ako"),
    ("until what time are you open today", "hanggang anong oras kayo bukas ngayon",
     "hangtod pila ka oras mo abri karon", "tubtob ano oras kamo bukas subong",
     "tubtob ano oras kamo bukas yana", "sagkod anong oras kamo bukas ngunyan"),
    ("what are your opening hours on Saturday?", "ano ang oras ninyo sa Sabado?",
     "unsa inyong oras sa Sabado?", "ano ang oras ninyo sa Sabado bala?",
     "ano an iyo oras han Sabado?", "ano an oras nindo sa Sabado?"),
    ("are you open already this early?", "bukas na ba kayo ng ganitong kaaga?",
     "abri na ba mo ingon ani ka sayo?", "bukas na bala kamo sining kaaga?",
     "bukas na ba kamo hini nga kaaga?", "bukas na daw kamo maski temprano pa?"),
    ("do you open on holidays?", "bukas ba kayo kapag holiday?", "abri ba mo kung holiday?",
     "bukas bala kamo kon holiday?", "bukas ba kamo kon holiday?", "bukas daw kamo pag holiday?"),
]  # fmt: skip

PRICES: list[Row] = [
    ("how much is the bibingka?", "magkano ang bibingka?", "pila ang bibingka?",
     "tagpila ang bibingka?", "tagpira an bibingka?", "magkano an bibingka?"),
    ("how much are bibingka and puto bumbong", "magkano ang bibingka at puto bumbong",
     "pila ang bibingka ug puto bumbong", "tagpila ang bibingka kag puto bumbong",
     "tagpira an bibingka ngan puto bumbong", "magkano an bibingka asin puto bumbong"),
    ("can I see your menu?", "pwede po makita ang menu?", "pwede makita ang menu?",
     "pwede makita ang menu ninyo?", "pwede makita an menu niyo?", "pwede mahiling an menu nindo?"),
    ("price of the special?", "presyo ng special?", "presyo sa special?", "presyo sang special?",
     "presyo han special?", "presyo kan special?"),
    ("hm salted egg po", "hm po ang salted egg", "hm ang salted egg", "hm ang salted egg bala",
     "hm an salted egg", "hm an salted egg tabi"),
    ("what's the price list", "ano ang price list ninyo", "unsa inyong price list",
     "ano ang price list ninyo bala", "ano an price list niyo", "ano an price list nindo"),
    ("how much for a box of 4?", "magkano ang box of 4?", "pila ang box of 4?",
     "tagpila ang box of 4?", "tagpira an box of 4?", "magkano an box of 4?"),
    ("is the cheese overload more expensive than the classic?",
     "mas mahal ba ang cheese overload kaysa classic?",
     "mas mahal ba ang cheese overload kay sa classic?",
     "mas mahal bala ang cheese overload sang sa classic?",
     "mas mahal ba an cheese overload kaysa classic?",
     "mas mahal daw an cheese overload kaysa classic?"),
    ("how much is the ube bibingka", "magkano ang ube na bibingka", "pila ang ube nga bibingka",
     "tagpila ang ube nga bibingka", "tagpira an ube nga bibingka", "magkano an ube na bibingka"),
    ("do you have coffee? how much", "may kape kayo? magkano", "naa moy kape? pila",
     "may kape kamo? tagpila", "may-ada kamo kape? tagpira", "igwa kamong kape? magkano"),
]  # fmt: skip

# Each order seed: ((item, quantity), ...), the time, the day offset, then the six texts.
OrderRow = tuple[tuple[tuple[str, int], ...], str, str, str, str, str, str, str, str]
PLACE_ORDER: list[OrderRow] = [
    ((("Classic", 10),), "08:00", "+1d",
     "I'd like to order 10 bibingka, pickup tomorrow 8am",
     "pa-order po 10 bibingka, pickup bukas 8am", "pa-order ko 10 bibingka, kuhaon ugma 8am",
     "pa-order ako 10 bibingka, kuhaon buwas 8am", "pa-order ako 10 bibingka, kukuhaon buwas 8am",
     "pa-order ako 10 bibingka, kukuanon sa aga 8am"),
    ((("Special", 5), ("Ube", 5)), "15:00", "+0d",
     "order 5 special and 5 ube for pickup at 3pm today",
     "order ko 5 special at 5 ube, kukunin ko ngayon 3pm",
     "order ko 5 special ug 5 ube, kuhaon nako karon 3pm",
     "order ko 5 special kag 5 ube, kuhaon ko subong 3pm",
     "order ko 5 special ngan 5 ube, kukuhaon ko yana 3pm",
     "order ko 5 special asin 5 ube, kukuanon ko ngunyan 3pm"),
    ((("Classic", 20),), "10:00", "+1d",
     "can I order 20 classic for delivery to Marikina tomorrow at 10am?",
     "pwede pa-deliver ng 20 classic sa Marikina bukas ng 10am?",
     "pwede pa-deliver og 20 classic sa Marikina ugma 10am?",
     "pwede pa-deliver sang 20 classic sa Marikina buwas 10am?",
     "pwede pa-deliver hin 20 classic ha Marikina buwas 10am?",
     "pwede pa-deliver nin 20 classic sa Marikina sa aga 10am?"),
    ((("Cheese overload", 2), ("Salted egg", 3)), "09:00", "+4d",
     "2 cheese overload and 3 salted egg, I'll pick up Saturday 9am",
     "2 cheese overload at 3 salted egg po, kukunin ko sa Sabado 9am",
     "2 cheese overload ug 3 salted egg, kuhaon nako sa Sabado 9am",
     "2 cheese overload kag 3 salted egg, kuhaon ko sa Sabado 9am",
     "2 cheese overload ngan 3 salted egg, kukuhaon ko han Sabado 9am",
     "2 cheese overload asin 3 salted egg, kukuanon ko sa Sabado 9am"),
    ((("Classic", 12),), "16:00", "+0d",
     "please reserve 12 bibingka for 4pm pickup today",
     "pa-reserve po ng 12 bibingka, kukunin mamayang alas 4",
     "pa-reserve og 12 bibingka, kuhaon unya alas 4",
     "pa-reserve sang 12 bibingka, kuhaon ko alas 4 subong",
     "pa-reserve hin 12 bibingka, kukuhaon ko alas 4 yana",
     "pa-reserve nin 12 bibingka, kukuanon ko alas 4 ngunyan"),
    ((("Ube", 6), ("Special", 6)), "14:00", "+1d",
     "order 6 ube 6 special pickup tomorrow 2pm", "order 6 ube 6 special pickup bukas 2pm",
     "order 6 ube 6 special kuhaon ugma 2pm", "order 6 ube 6 special kuhaon buwas 2pm",
     "order 6 ube 6 special kukuhaon buwas 2pm", "order 6 ube 6 special kukuanon sa aga 2pm"),
    ((("Classic", 30),), "11:00", "+3d",
     "can I get 30 classic delivered to Pasig on Friday at 11am?",
     "pwede po bang 30 classic, i-deliver sa Pasig sa Biyernes 11am?",
     "pwede 30 classic, i-deliver sa Pasig sa Biyernes 11am?",
     "pwede 30 classic, i-deliver sa Pasig sa Biyernes 11am bala?",
     "pwede 30 classic, i-deliver ha Pasig han Biyernes 11am?",
     "pwede daw 30 classic, i-deliver sa Pasig sa Biyernes 11am?"),
    ((("Puto bumbong", 4), ("Kape", 2)), "17:30", "+0d",
     "4 puto bumbong and 2 kape for pickup at 5:30pm today",
     "4 puto bumbong at 2 kape, kukunin ko ngayon 5:30pm",
     "4 puto bumbong ug 2 kape, kuhaon nako karon 5:30pm",
     "4 puto bumbong kag 2 kape, kuhaon ko subong 5:30pm",
     "4 puto bumbong ngan 2 kape, kukuhaon ko yana 5:30pm",
     "4 puto bumbong asin 2 kape, kukuanon ko ngunyan 5:30pm"),
    ((("Classic", 15),), "13:00", "+1d",
     "order 15 classic, deliver to Quezon City tomorrow 1pm",
     "order po 15 classic, deliver sa Quezon City bukas 1pm",
     "order 15 classic, i-deliver sa Quezon City ugma 1pm",
     "order 15 classic, i-deliver sa Quezon City buwas 1pm",
     "order 15 classic, i-deliver ha Quezon City buwas 1pm",
     "order 15 classic, i-deliver sa Quezon City sa aga 1pm"),
    ((("Special", 8),), "18:00", "+0d",
     "I want to buy 8 special, I'll get them at 6pm tonight",
     "pabili ng 8 special, kukunin ko mamayang alas 6",
     "palit ko 8 special, kuhaon nako unya alas 6",
     "bakal ko 8 special, kuhaon ko alas 6 subong",
     "papalit ako 8 special, kukuhaon ko alas 6 yana",
     "mabakal ako 8 special, kukuanon ko alas 6 ngunyan"),
]  # fmt: skip

ORDER_STATUS: list[Row] = [
    ("is my order ready?", "ready na ba order ko?", "andam na ba akong order?",
     "handa na bala ang order ko?", "andam na ba an akon order?", "lista na daw an order ko?"),
    ("what's the status of my order", "ano na status ng order ko",
     "unsa na ang status sa akong order", "ano na ang status sang order ko",
     "ano na an status han akon order", "ano na an status kan order ko"),
    ("has my order been confirmed?", "confirmed na ba ang order ko?",
     "na-confirm na ba akong order?", "na-confirm na bala ang order ko?",
     "na-confirm na ba an akon order?", "na-confirm na daw an order ko?"),
    ("can I pick up my order now?", "pwede ko na bang kunin ang order ko?",
     "pwede na nako kuhaon akong order?", "pwede ko na bala kuhaon ang order ko?",
     "pwede ko na ba kuhaon an akon order?", "pwede ko na daw kuanon an order ko?"),
    ("any update on my order po?", "may update na po ba sa order ko?",
     "naa nay update sa akong order?", "may update na bala sa order ko?",
     "may-ada na update han akon order?", "igwa na daw update sa order ko?"),
    ("did you receive my order?", "natanggap nyo ba order ko?", "nadawat ba ninyo akong order?",
     "nabaton ninyo bala ang order ko?", "nakarawat niyo ba an akon order?",
     "nakua nindo daw an order ko?"),
    ("where is my delivery?", "nasaan na ang delivery ko?", "asa na akong delivery?",
     "diin na ang delivery ko?", "hain na an akon delivery?", "hain na an delivery ko?"),
    ("is the bibingka I ordered done?", "luto na ba yung bibingka na inorder ko?",
     "luto na ba ang bibingka nga akong gi-order?", "luto na bala ang bibingka nga gin-order ko?",
     "luto na ba an bibingka nga akon gin-order?", "luto na daw an bibingka na inorder ko?"),
    ("check my order please", "pa-check po ng order ko", "palihug check sa akong order",
     "palihog check sang order ko", "alayon check han akon order", "paki-check an order ko"),
    ("how long until my order is ready?", "gaano pa katagal bago ma-ready ang order ko?",
     "dugay pa ba ma-ready akong order?", "madugay pa bala antes ma-ready ang order ko?",
     "maiha pa ba antes ma-ready an akon order?", "haloy pa daw bago ma-ready an order ko?"),
]  # fmt: skip

DELIVERY_AREA: list[Row] = [
    ("do you deliver to Marikina?", "nagdedeliver ba kayo sa Marikina?",
     "nag-deliver ba mo sa Marikina?", "nagadeliver bala kamo sa Marikina?",
     "nagdedeliver ba kamo ha Marikina?", "nagdedeliver daw kamo sa Marikina?"),
    ("how much is the delivery fee to Pasig?", "magkano ang delivery fee sa Pasig?",
     "pila ang delivery fee sa Pasig?", "tagpila ang delivery fee pa-Pasig?",
     "tagpira an delivery fee ha Pasig?", "magkano an delivery fee pasiring Pasig?"),
    ("do you have delivery?", "may delivery ba kayo?", "naa ba moy delivery?",
     "may delivery bala kamo?", "may-ada ba kamo delivery?", "igwa daw kamong delivery?"),
    ("can you deliver to Antipolo?", "pwede ba mag-deliver sa Antipolo?",
     "pwede ba mo mo-deliver sa Antipolo?", "pwede bala kamo mag-deliver sa Antipolo?",
     "pwede ba kamo mag-deliver ha Antipolo?", "pwede daw kamo mag-deliver sa Antipolo?"),
    ("what areas do you deliver to", "saang lugar kayo nagdedeliver",
     "asa nga mga lugar mo mo-deliver", "diin nga mga lugar kamo nagadeliver",
     "ano nga mga lugar kamo nagdedeliver", "saen na mga lugar kamo nagdedeliver"),
    ("is Quezon City within your delivery area?", "sakop ba ng delivery ninyo ang Quezon City?",
     "sakop ba sa inyong delivery ang Quezon City?",
     "sakop bala sang delivery ninyo ang Quezon City?",
     "sakop ba han iyo delivery an Quezon City?", "sakop daw kan delivery nindo an Quezon City?"),
    ("delivery to Cainta possible?", "pwede ba delivery sa Cainta?",
     "posible ba delivery sa Cainta?", "pwede bala delivery sa Cainta?",
     "pwede ba delivery ha Cainta?", "pwede daw delivery sa Cainta?"),
    ("how much to deliver to Marikina", "magkano kung ipapadala sa Marikina",
     "pila kung ipadala sa Marikina", "tagpila kon ipadala sa Marikina",
     "tagpira kon ipadara ha Marikina", "magkano kun ipapadara sa Marikina"),
    ("do you deliver here in San Mateo?", "nagdedeliver ba kayo dito sa San Mateo?",
     "nag-deliver ba mo diri sa San Mateo?", "nagadeliver bala kamo diri sa San Mateo?",
     "nagdedeliver ba kamo dinhi ha San Mateo?", "nagdedeliver daw kamo digdi sa San Mateo?"),
    ("is there a minimum for delivery to Pasig?", "may minimum ba para ma-deliver sa Pasig?",
     "naa bay minimum para ma-deliver sa Pasig?", "may minimum bala para ma-deliver sa Pasig?",
     "may-ada ba minimum para ma-deliver ha Pasig?", "igwa daw minimum para ma-deliver sa Pasig?"),
]  # fmt: skip

COMPLAINT: list[Row] = [
    ("the bibingka yesterday was so hard", "sobrang tigas ng bibingka kahapon",
     "gahi kaayo ang bibingka gahapon", "gahi gid ang bibingka kahapon",
     "gahi hin duro an bibingka kakulop", "matagas na marhay an bibingka kasuhapon"),
    ("my order was short by 2 pieces", "kulang ng 2 piraso ang order ko",
     "kulang og 2 ka buok akong order", "kulang sang 2 ka buok ang order ko",
     "kulang hin 2 ka buok an akon order", "kulang nin 2 piraso an order ko"),
    ("the delivery was very late, not happy", "sobrang late ng delivery, hindi ako masaya",
     "late kaayo ang delivery, dili ko malipay", "late gid ang delivery, indi ako malipayon",
     "late hin duro an delivery, diri ako malipay", "late na marhay an delivery, dai ako maogma"),
    ("you gave me the wrong order", "mali ang binigay ninyong order",
     "sayop ang order nga gihatag ninyo", "sala ang order nga gin-hatag ninyo",
     "sayop an order nga iginhatag niyo", "sala an order na itinao nindo"),
    ("the puto bumbong was spoiled", "sira na ang puto bumbong", "panis na ang puto bumbong",
     "napanis na ang puto bumbong", "panis na an puto bumbong", "panis na an puto bumbong tabi"),
    ("the cashier was rude to me", "ang sungit ng cashier sa akin",
     "bastos kaayo ang cashier nako", "bastos gid ang cashier sa akon",
     "bastos an cashier ha akon", "bastos an cashier sako"),
    ("the bibingka was cold when I picked it up", "malamig na ang bibingka nung kinuha ko",
     "bugnaw na ang bibingka pagkuha nako", "matugnaw na ang bibingka sang ginkuha ko",
     "mahagkot na an bibingka han akon kinuha", "malipot na an bibingka kan kinua ko"),
    ("I want to complain about my order", "gusto ko pong magreklamo tungkol sa order ko",
     "gusto ko mo-reklamo bahin sa akong order", "gusto ko magreklamo parte sa order ko",
     "karuyag ko magreklamo mahitungod han akon order",
     "gusto kong magreklamo manongod sa order ko"),
    ("the salted egg tasted sour", "maasim ang lasa ng salted egg",
     "aslom ang lasa sa salted egg", "maaslum ang lasa sang salted egg",
     "maaslum an lasa han salted egg", "maalsom an lasa kan salted egg"),
    ("waited an hour for my pickup, terrible service",
     "isang oras akong naghintay sa pickup, ang pangit ng serbisyo",
     "usa ka oras ko naghulat sa pickup, pangit kaayo ang serbisyo",
     "isa ka oras ako naghulat sa pickup, malain gid ang serbisyo",
     "usa ka oras ako naghulat han pickup, maraot an serbisyo",
     "sarong oras akong naghalat sa pickup, maraot an serbisyo"),
]  # fmt: skip

CANCEL_ORDER: list[Row] = [
    ("please cancel my order", "pakicancel po ng order ko", "palihug i-cancel akong order",
     "palihog i-cancel ang order ko", "alayon i-cancel an akon order", "paki-cancel an order ko"),
    ("never mind, cancel it", "cancel na lang po", "cancel na lang", "i-cancel na lang",
     "kanselahon na la", "cancel na sana"),
    ("I don't need the order anymore", "hindi ko na kailangan ang order",
     "dili na nako kinahanglan ang order", "indi ko na kinahanglan ang order",
     "diri ko na kinahanglan an order", "dai ko na kaipuhan an order"),
    ("cancel my pickup tomorrow", "i-cancel ang pickup ko bukas", "i-cancel akong pickup ugma",
     "i-cancel ang pickup ko buwas", "i-cancel an akon pickup buwas", "i-cancel an pickup ko sa aga"),
    ("don't push through with my order, I changed my mind",
     "huwag na po ituloy ang order, nagbago isip ko",
     "ayaw na ituloy ang order, nausab akong hunahuna",
     "indi na pagpadayunon ang order, nagbag-o ang hunahuna ko",
     "ayaw na ipadayon an order, nagbag-o an akon hunahuna",
     "dai na ipadagos an order, nagbago an isip ko"),
    ("I want to cancel", "gusto ko i-cancel", "gusto nako i-cancel", "gusto ko i-cancel bala",
     "karuyag ko i-cancel", "gusto kong i-cancel"),
    ("cancel the delivery please, we won't be home", "pakicancel ang delivery, wala kami sa bahay",
     "palihug cancel sa delivery, wala mi sa balay", "palihog cancel ang delivery, wala kami sa balay",
     "alayon cancel an delivery, waray kami ha balay", "paki-cancel an delivery, mayo kami sa harong"),
    ("can I still cancel my order?", "pwede ko pa bang i-cancel ang order ko?",
     "pwede pa ba nako i-cancel akong order?", "pwede ko pa bala i-cancel ang order ko?",
     "pwede ko pa ba i-cancel an akon order?", "pwede ko pa daw i-cancel an order ko?"),
    ("scrap my order", "i-void na lang ang order ko", "i-void na lang akong order",
     "i-void na lang ang order ko bala", "i-void na la an akon order", "i-void na sana an order ko"),
    ("sorry, please cancel the bibingka I ordered", "sorry, pakicancel yung bibingka na inorder ko",
     "sorry, palihug cancel sa bibingka nga akong gi-order",
     "sorry, palihog cancel ang bibingka nga gin-order ko",
     "sorry, alayon cancel an bibingka nga akon gin-order", "sorry, paki-cancel an bibingka na inorder ko"),
]  # fmt: skip

# Scenario 8, the staff side: seeds 0 to 3 ask today's orders, 4 to 6 mark one ready, 7 to 9
# say it was picked up (each action in both halves). Mila's 15:00 order is today's only one.
STAFF_ACTIONS = (
    *["staff_orders_today"] * 4, *["staff_mark_ready"] * 3, *["staff_mark_picked_up"] * 3,
)  # fmt: skip
STAFF: list[Row] = [
    ("orders today", "ano ang orders ngayon", "unsa ang mga order karon",
     "ano ang mga order subong", "ano an mga order yana", "ano an mga order ngunyan"),
    ("who is picking up today?", "sino ang kukuha ngayon?", "kinsa ang mokuha karon?",
     "sin-o ang makuha subong?", "hin-o an makuha yana?", "siisay an makua ngunyan?"),
    ("list of customer orders for today please", "pakilista ng customer orders para ngayon",
     "palihug ilista ang customer orders para karon",
     "palihog ilista ang customer orders para subong",
     "alayon ilista an customer orders para yana", "paki-lista an customer orders para ngunyan"),
    ("any pickups this afternoon?", "may pickup ba mamayang hapon?", "naay pickup karong hapon?",
     "may pickup bala sa hapon?", "may-ada pickup yana nga kulop?",
     "igwa daw pickup ngunyan na hapon?"),
    ("Mila's order is ready", "ready na yung kay Mila", "andam na ang kang Mila",
     "handa na ang kay Mila", "andam na an kan Mila", "lista na an ki Mila"),
    ("the order is done, ready for pickup", "tapos na ang order, ready na for pickup",
     "human na ang order, andam na kuhaon", "tapos na ang order, handa na kuhaon",
     "human na an order, andam na kuhaon", "tapos na an order, lista nang kuanon"),
    ("the 10 classic for 3pm is packed and ready", "naka-pack na ang 10 classic para 3pm, ready na",
     "naka-pack na ang 10 classic para 3pm, andam na",
     "naka-pack na ang 10 classic para 3pm, handa na",
     "naka-pack na an 10 classic para 3pm, andam na", "naka-pack na an 10 classic para 3pm, lista na"),
    ("the customer picked up the order", "picked up na", "nakuha na sa customer",
     "nakuha na sang customer", "nakuha na han customer", "nakua na kan customer"),
    ("Mila already collected her order", "nakuha na ni Mila ang order niya",
     "nakuha na ni Mila iyang order", "nakuha na ni Mila ang iya order",
     "nakuha na ni Mila an iya order", "nakua na ni Mila an order niya"),
    ("order collected, close it", "kinuha na ang order, isara na", "nakuha na ang order, sirado na",
     "nakuha na ang order, isara na", "nakuha na an order, sirad-a na", "nakua na an order, isara na"),
]  # fmt: skip

SEEDS: dict[str, list[Row]] = {
    "hours": HOURS,
    "prices": PRICES,
    "order_status": ORDER_STATUS,
    "delivery_area": DELIVERY_AREA,
    "complaint": COMPLAINT,
    "cancel_order": CANCEL_ORDER,
}
SCENARIOS = ("hours", "prices", "place_order", *list(SEEDS)[2:], "staff")


def _half(seed: int) -> Literal["tune", "gate"]:
    return "tune" if seed % 2 == 0 else "gate"


CASES: list[Case] = [
    *[
        Case(lang, scenario, text, scenario, "customer", half=_half(i))
        for scenario, rows in SEEDS.items()
        for i, texts in enumerate(rows)
        for lang, text in zip(GATED_LANGS, texts, strict=True)
    ],
    *[
        Case(
            lang, "place_order", text, "place_order", "customer", half=_half(i),
            expected_lines=lines, expected_time=time, expected_day=day,
        )
        for i, (lines, time, day, *texts) in enumerate(PLACE_ORDER)
        for lang, text in zip(GATED_LANGS, texts, strict=True)
    ],
    *[
        Case(lang, "staff", text, action, "supervisor" if i >= 8 else "clerk", half=_half(i))
        for i, (action, texts) in enumerate(zip(STAFF_ACTIONS, STAFF, strict=True))
        for lang, text in zip(GATED_LANGS, texts, strict=True)
    ],
]  # fmt: skip
