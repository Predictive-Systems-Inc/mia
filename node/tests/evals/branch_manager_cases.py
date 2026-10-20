"""The branch manager decider eval set (spec 2026-10-19-branch-manager, scenarios 3 to 7, and the
weekly summary, monthly letter, short code and keep asks): what Ferino's owner, head staff and
clerks send, ten messages per scenario in each gated language, split into halves by seed (even
seeds tune, odd seeds gate; a seed's languages share a half, so no text is in both). Data only;
test_branch_manager_evals.py runs it.

Synthetic, written by Claude, not native speakers (D18). English seeds come first; the five
Philippine languages are drafts for an owner or a clerk texting on a phone, and Q28 to Q35
cover their review. Items are named as clerks type them (Classic, Salted egg, Box of 4), never
"bibingka" alone (a short code, not an item). Typed experiments cover every strategy kind
(price: charm, anchor, increase, decoy; promo: volume, markdown, seasonal; bundle) and some name
no strategy. Prices are digits find_prices reads; a price change names its day with a word
find_dates reads (a weekday, "Nov 1", "Nobyembre 2", bukas, ugma, buwas, sa aga). The run pins
today to TODAY, the bm fixture's Monday, so the weekdays resolve the same on every run; the
shape test checks each expected price, date and short code is a candidate code gives Jev."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str
    role: str  # a role of a seeded Ferino's person (clerk Ana, supervisor Marites, owner Rosa)
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "gate"] = "tune"
    # item (a seeded item name), price (minor units), code, keep, strategy (a name_key's last
    # part, reported only), kind (price, promo or bundle, reported only)
    expected: dict[str, Any] = field(default_factory=dict)


GATED_LANGS = ("en", "fil", "ceb", "hil", "war", "bcl")
TODAY = dt.date(2026, 10, 26)  # a Monday, the bm fixture's day

Row = tuple[dict[str, Any], str, str, str, str, str, str]  # expected, then en fil ceb hil war bcl
NONE: dict[str, Any] = {}


def _x(item: str, pesos: int, kind: str, strategy: str = "") -> dict[str, Any]:
    return {"item": item, "price": pesos * 100, "kind": kind, "strategy": strategy}


def _p(item: str, pesos: int) -> dict[str, Any]:
    return {"item": item, "price": pesos * 100}


COACHING: list[Row] = [
    (NONE, "who is good at selling salted egg?", "sino magaling magbenta ng salted egg?",
     "kinsa ang maayo mobaligya og salted egg?", "sin-o ang maayo magbaligya sang salted egg?",
     "hin-o an maupay magbaligya hin salted egg?", "siisay an magaling magbenta kan salted egg?"),
    (NONE, "how is Ana doing with her sales?", "kumusta ang benta ni Ana?",
     "kumusta ang baligya ni Ana?", "kamusta ang baligya ni Ana?", "kumusta an baligya ni Ana?",
     "kumusta an benta ni Ana?"),
    (NONE, "who on the team needs help selling?",
     "sino sa team ang kailangan ng tulong sa pagbenta?",
     "kinsa sa team ang nanginahanglan og tabang sa pagbaligya?",
     "sin-o sa team ang nagakinahanglan sang bulig sa pagbaligya?",
     "hin-o ha team an nagkikinahanglan hin bulig ha pagbaligya?",
     "siisay sa team an nangangaipo nin tabang sa pagbenta?"),
    (NONE, "which clerk improved the most this month?",
     "sinong clerk ang pinakagumaling ngayong buwan?",
     "kinsang clerk ang labing nindot og uswag karong bulana?",
     "sin-o nga clerk ang pinakanag-uswag subong nga bulan?",
     "hin-o nga clerk an gimaopay an pag-uswag yana nga bulan?",
     "siisay na clerk an pinakanag-uswag ngunyan na bulan?"),
    (NONE, "is Liza falling behind her target?", "naiiwan ba si Liza sa target niya?",
     "nagpaiwi ba si Liza sa iyang target?", "nagaulihi bala si Liza sa iya target?",
     "naiiwan ba hi Liza ha iya target?", "napapaatras daw si Liza sa target niya?"),
    (NONE, "coaching report for my clerks please", "pakita ang coaching ng mga clerk ko",
     "ipakita ang coaching sa akong mga clerk", "ipakita ang coaching sang akon mga clerk",
     "ipakita an coaching han akon mga clerk", "ipahiling an coaching kan mga clerk ko"),
    (NONE, "who sells the most Box of 4 among the clerks?",
     "sino sa mga clerk ang pinakamaraming nabentang Box of 4?",
     "kinsa sa mga clerk ang pinakadaghan nakabaligya og Box of 4?",
     "sin-o sa mga clerk ang pinakadamo nakabaligya sang Box of 4?",
     "hin-o ha mga clerk an gidamoi nakabaligya hin Box of 4?",
     "siisay sa mga clerk an pinakadakol nabentang Box of 4?"),
    (NONE, "how is Pao doing compared to last month?",
     "kumusta si Pao kumpara noong nakaraang buwan?", "kumusta si Pao kumpara sa miaging bulan?",
     "kamusta si Pao kumpara sang nagligad nga bulan?",
     "kumusta hi Pao kumpara han nakalabay nga bulan?",
     "kumusta si Pao kumpara kan nakaaging bulan?"),
    (NONE, "who needs coaching this week?", "sino ang kailangang i-coach ngayong linggo?",
     "kinsa ang kinahanglan i-coach karong semanaha?",
     "sin-o ang kinahanglan i-coach subong nga semana?",
     "hin-o an kinahanglan i-coach yana nga semana?",
     "siisay an kaipuhan i-coach ngunyan na semana?"),
    (NONE, "which of my clerks is doing best right now?",
     "sino sa mga clerk ko ang pinakamagaling ngayon?",
     "kinsa sa akong mga clerk ang labing maayo karon?",
     "sin-o sa akon mga clerk ang pinakamaayo subong?",
     "hin-o ha akon mga clerk an gimaopayi yana?",
     "siisay sa mga clerk ko an pinakamarhay ngunyan?"),
]  # fmt: skip

HOW_TO_SELL: list[Row] = [
    ({"item": "Salted egg"}, "how do I sell more salted egg?", "paano ko mabebenta ang salted egg?",
     "unsaon nako pagbaligya og daghang salted egg?", "paano ko mabaligya ang salted egg?",
     "paonan-o ko mabaligya an salted egg?", "paano ko mabebenta an salted egg?"),
    ({"item": "Ube"}, "any tips to sell the ube?", "may tips ka para mabenta ang ube?",
     "naa kay tips para mabaligya ang ube?", "may tips ka para mabaligya ang ube?",
     "may-ada ka tips para mabaligya an ube?", "igwa kang tips para mabenta an ube?"),
    ({"item": "Puto bumbong"}, "puto bumbong is slow today, what should I say to customers?",
     "mabagal ang puto bumbong ngayon, ano ang sasabihin ko sa customer?",
     "hinay ang puto bumbong karon, unsay akong isulti sa customer?",
     "mahinay ang puto bumbong subong, ano ang akon isiling sa customer?",
     "mahinay an puto bumbong yana, ano an akon isusumat ha customer?",
     "makulse an puto bumbong ngunyan, ano an sasabihon ko sa customer?"),
    ({"item": "Cheese overload"}, "how can I offer the cheese overload better?",
     "paano ko mas maaalok ang cheese overload?",
     "unsaon nako pagtanyag og maayo ang cheese overload?",
     "paano ko matanyag sing maayo ang cheese overload?",
     "paonan-o ko maitanyag hin maupay an cheese overload?",
     "paano ko maaalok nin mas marhay an cheese overload?"),
    ({"item": "Box of 4"}, "tips for selling Box of 4 to families?",
     "tips sa pagbenta ng Box of 4 sa mga pamilya?", "tips sa pagbaligya og Box of 4 sa mga pamilya?",
     "tips sa pagbaligya sang Box of 4 sa mga pamilya?",
     "tips ha pagbaligya hin Box of 4 ha mga pamilya?",
     "tips sa pagbenta kan Box of 4 sa mga pamilya?"),
    ({"item": "Kape"}, "how do I get customers to add a kape?",
     "paano ko mapapabili ng kape ang mga customer?", "unsaon nako pagpapalit sa customer og kape?",
     "paano ko mapabakal sang kape ang mga customer?",
     "paonan-o ko mapapalit hin kape an mga customer?",
     "paano ko mapabakal nin kape an mga customer?"),
    ({"item": "Special"}, "help me sell more Special",
     "tulungan mo akong makabenta ng mas maraming Special",
     "tabangi ko nga makabaligya og mas daghang Special",
     "buligi ako nga makabaligya sang mas madamo nga Special",
     "buligi ako nga makabaligya hin mas damo nga Special",
     "tabangi ako na makabenta nin mas dakol na Special"),
    ({"item": "Classic"}, "what's a good line to sell the classic?",
     "ano ang magandang sabihin para mabenta ang classic?",
     "unsay maayong isulti para mabaligya ang classic?",
     "ano ang maayo nga isiling para mabaligya ang classic?",
     "ano an maupay nga isumat para mabaligya an classic?",
     "ano an marhay na sabihon para mabenta an classic?"),
    ({"item": "Salted egg"}, "nobody buys salted egg in the afternoon, any advice?",
     "walang bumibili ng salted egg sa hapon, may payo ka?",
     "walay mopalit og salted egg sa hapon, naa kay tambag?",
     "wala nagabakal sang salted egg sa hapon, may laygay ka?",
     "waray namamalit hin salted egg ha kulop, may-ada ka tambag?",
     "mayong nagbabakal nin salted egg sa hapon, igwa kang hatol?"),
    ({"item": "Ube"}, "how should I upsell ube to regulars?", "paano ko ia-upsell ang ube sa mga suki?",
     "unsaon nako pag-upsell sa ube sa mga suki?", "paano ko ma-upsell ang ube sa mga suki?",
     "paonan-o ko ma-upsell an ube ha mga suki?", "paano ko ma-upsell an ube sa mga suki?"),
]  # fmt: skip

EXPERIMENT_PRICE: list[Row] = [
    (_x("Classic", 39, "price", "charm"), "let's try Classic at 39 for two weeks",
     "subukan natin 39 ang Classic ng dalawang linggo",
     "sulayan nato og 39 ang Classic sulod sa duha ka semana",
     "tilawan naton sang 39 ang Classic sa duha ka semana",
     "testingan naton hin 39 an Classic ha duha ka semana",
     "probaran ta 39 an Classic sa duwang semana"),
    (_x("Salted egg", 49, "price", "charm"), "test salted egg at 49 instead of 50",
     "i-test natin ang salted egg sa 49 imbes na 50", "i-test nato ang salted egg sa 49 imbes 50",
     "i-test naton ang salted egg sa 49 imbes sang 50",
     "i-test naton an salted egg ha 49 imbes nga 50", "i-test ta an salted egg sa 49 imbes na 50"),
    (_x("Special", 49, "price", "increase"), "Special always sells out, let's test it at 49",
     "laging ubos ang Special, subukan natin sa 49", "permi mahurot ang Special, sulayan nato sa 49",
     "pirme nauubos ang Special, tilawan naton sa 49",
     "pirme nauubos an Special, testingan naton ha 49", "pirmi nauubos an Special, probaran ta sa 49"),
    (_x("Cheese overload", 65, "price", "anchor"),
     "try cheese overload at 65 as the premium one next to the regular",
     "subukan natin ang cheese overload sa 65 bilang premium katabi ng regular",
     "sulayan ang cheese overload sa 65 isip premium tupad sa regular",
     "tilawan ang cheese overload sa 65 nga premium tupad sang regular",
     "testingan an cheese overload ha 65 sugad nga premium ha tupad han regular",
     "probaran an cheese overload sa 65 bilang premium sa lado kan regular"),
    (_x("Puto bumbong", 39, "price"), "experiment: puto bumbong at 39 starting Monday",
     "experiment: puto bumbong sa 39 simula Lunes", "experiment: puto bumbong sa 39 sugod Lunes",
     "experiment: puto bumbong sa 39 umpisa sa Lunes",
     "experiment: puto bumbong ha 39 tikang Lunes", "experiment: puto bumbong sa 39 poon Lunes"),
    (_x("Kape", 29, "price", "charm"), "can we try kape at 29 for a while?",
     "pwede ba nating subukan ang kape sa 29 muna?",
     "pwede ba nato sulayan ang kape sa 29 sa makadiyot?",
     "pwede bala naton tilawan ang kape sa 29 anay?", "puydi ba naton testingan an kape ha 29 anay?",
     "pwede ta daw probaran an kape sa 29 muna?"),
    (_x("Ube", 49, "price", "decoy"), "test Ube at 49 as the middle of three sizes",
     "i-test ang Ube sa 49 bilang gitna ng tatlong size",
     "i-test ang Ube sa 49 isip tunga sa tulo ka size",
     "i-test ang Ube sa 49 nga tunga sang tatlo ka size",
     "i-test an Ube ha 49 sugad nga butnga han tulo nga size",
     "i-test an Ube sa 49 bilang tahaw kan tulong size"),
    (_x("Classic", 44, "price", "increase"), "Classic sells out by noon, try 44 for two weeks",
     "ubos na ang Classic bago magtanghali, subukan ang 44 ng dalawang linggo",
     "mahurot ang Classic una sa udto, sulayi ang 44 sulod duha ka semana",
     "nauubos ang Classic antes sang udto, tilawi ang 44 sa duha ka semana",
     "nauubos an Classic antes han udto, testingi an 44 ha duha ka semana",
     "nauubos an Classic bago mag-udto, probari an 44 sa duwang semana"),
    (_x("Salted egg", 55, "price", "increase"), "I'd like to propose salted egg at 55 as a test",
     "gusto kong i-propose na i-test ang salted egg sa 55",
     "gusto nako i-propose nga i-test ang salted egg sa 55",
     "gusto ko i-propose nga i-test ang salted egg sa 55",
     "karuyag ko i-propose nga i-test an salted egg ha 55",
     "gusto kong i-propose na i-test an salted egg sa 55"),
    (_x("Special", 44, "price"), "can we trial Special at 44 to see if it moves faster?",
     "pwede bang i-trial ang Special sa 44 para makita kung mas mabilis mabenta?",
     "pwede ba i-trial ang Special sa 44 aron makita kung mas paspas mabaligya?",
     "pwede bala i-trial ang Special sa 44 para makita kon mas dasig mabaligya?",
     "puydi ba i-trial an Special ha 44 basi makita kun mas dali mabaligya?",
     "pwede daw i-trial an Special sa 44 tanganing mahiling kun mas dali mabenta?"),
]  # fmt: skip

EXPERIMENT_PROMO: list[Row] = [
    (_x("Classic", 110, "promo", "volume"), "let's test a promo: 3 Classic for 110",
     "i-promo natin: 3 Classic sa 110", "i-promo nato: 3 ka Classic sa 110",
     "i-promo naton: 3 ka Classic sa 110", "i-promo naton: 3 nga Classic ha 110",
     "i-promo ta: 3 na Classic sa 110"),
    (_x("Ube", 35, "promo", "markdown"),
     "markdown test: Ube at 35 after 6pm since we always have leftovers",
     "markdown test: Ube sa 35 pagkatapos ng 6pm kasi laging may tira",
     "markdown test: Ube sa 35 human sa 6pm kay permi may salin",
     "markdown test: Ube sa 35 pagkatapos sang 6pm kay pirme may nabilin",
     "markdown test: Ube ha 35 kahuman han 6pm kay pirme may-ada nahibilin",
     "markdown test: Ube sa 35 pagkatapos kan 6pm ta pirmi igwang tada"),
    (_x("Box of 4", 150, "bundle", "bundle"), "try Box of 4 at 150 as a bundle deal",
     "subukan ang Box of 4 sa 150 bilang bundle", "sulayi ang Box of 4 sa 150 isip bundle",
     "tilawi ang Box of 4 sa 150 nga bundle", "testingi an Box of 4 ha 150 sugad nga bundle",
     "probari an Box of 4 sa 150 bilang bundle"),
    (_x("Puto bumbong", 30, "promo", "seasonal"),
     "puto bumbong promo at 30 before Christmas, like last year",
     "promo ng puto bumbong sa 30 bago mag-Pasko, gaya noong nakaraang taon",
     "promo sa puto bumbong sa 30 una sa Pasko, sama sa miaging tuig",
     "promo sang puto bumbong sa 30 antes sang Paskwa, pareho sang nagligad nga tuig",
     "promo han puto bumbong ha 30 antes han Pasko, pariho han nakalabay nga tuig",
     "promo kan puto bumbong sa 30 bago an Pasko, kapareho kan nakaaging taon"),
    (_x("Kape", 45, "promo", "volume"), "test buy 2 kape for 45", "i-test ang 2 kape sa 45",
     "i-test ang 2 ka kape sa 45", "i-test ang 2 ka kape sa 45 lang", "i-test an 2 nga kape ha 45",
     "i-test an 2 na kape sa 45"),
    (_x("Special", 40, "promo", "markdown"),
     "promo for Special in the last hour before closing, 40 each",
     "promo sa Special sa huling oras bago magsara, 40 bawat isa",
     "promo sa Special sa katapusang oras una magsira, 40 matag usa",
     "promo sa Special sa katapusan nga oras antes magsira, 40 kada isa",
     "promo ha Special ha urhi nga oras antes magsira, 40 kada usa",
     "promo sa Special sa huring oras bago magsara, 40 kada saro"),
    (_x("Box of 4", 155, "bundle", "bundle"), "make a combo test: Box of 4 at 155 for this month",
     "combo test: Box of 4 sa 155 ngayong buwan", "combo test: Box of 4 sa 155 karong bulana",
     "combo test: Box of 4 sa 155 subong nga bulan", "combo test: Box of 4 ha 155 yana nga bulan",
     "combo test: Box of 4 sa 155 ngunyan na bulan"),
    (_x("Salted egg", 220, "promo", "volume"), "promo on salted egg, 5 pieces for 220",
     "promo sa salted egg, 5 piraso sa 220", "promo sa salted egg, 5 ka buok sa 220",
     "promo sa salted egg, 5 ka buok sa 220 lang", "promo ha salted egg, 5 ka buok ha 220",
     "promo sa salted egg, 5 na piraso sa 220"),
    (_x("Cheese overload", 50, "promo", "seasonal"),
     "seasonal promo for cheese overload at 50 for Undas",
     "seasonal promo ng cheese overload sa 50 para sa Undas",
     "seasonal promo sa cheese overload sa 50 para sa Undas",
     "seasonal promo sang cheese overload sa 50 para sa Undas",
     "seasonal promo han cheese overload ha 50 para ha Undas",
     "seasonal promo kan cheese overload sa 50 para sa Undas"),
    (_x("Classic", 32, "promo", "markdown"), "we keep throwing away Classic, test 32 after 7pm",
     "lagi tayong nagtatapon ng Classic, i-test ang 32 pagkalipas ng 7pm",
     "permi ta naglabay og Classic, i-test ang 32 human sa 7pm",
     "pirme kita nagahaboy sang Classic, i-test ang 32 pagkatapos sang 7pm",
     "pirme kita naglalabog hin Classic, i-test an 32 kahuman han 7pm",
     "pirmi kitang nagtatapon nin Classic, i-test an 32 pagkatapos kan 7pm"),
]  # fmt: skip

CHANGE_PRICE: list[Row] = [
    (_p("Classic", 42), "make Classic 42 starting Monday", "gawin nating 42 ang Classic simula Lunes",
     "himoon nato nga 42 ang Classic sugod Lunes", "himuon naton nga 42 ang Classic umpisa Lunes",
     "himoon naton nga 42 an Classic tikang Lunes", "gibohon tang 42 an Classic poon Lunes"),
    (_p("Special", 50), "change the price of Special to 50 from Nov 1",
     "palitan ang presyo ng Special sa 50 simula Nov 1",
     "usba ang presyo sa Special ngadto sa 50 sugod Nov 1",
     "bag-uha ang presyo sang Special sa 50 umpisa Nov 1",
     "bag-oha an presyo han Special ngadto ha 50 tikang Nov 1",
     "baguhon an presyo kan Special sa 50 poon Nov 1"),
    (_p("Kape", 30), "kape goes up to 30 from tomorrow, for good",
     "gawing 30 na ang kape simula bukas, permanente na",
     "himoa nga 30 na ang kape sugod ugma, permanente na",
     "himua nga 30 na ang kape umpisa buwas, permanente na",
     "himoa nga 30 na an kape tikang buwas, permanente na",
     "gibohon nang 30 an kape poon sa aga, permanente na"),
    (_p("Box of 4", 165), "new price for Box of 4: 165 from Saturday",
     "bagong presyo ng Box of 4: 165 simula Sabado", "bag-ong presyo sa Box of 4: 165 sugod Sabado",
     "bag-o nga presyo sang Box of 4: 165 umpisa Sabado",
     "bag-o nga presyo han Box of 4: 165 tikang Sabado", "bagong presyo kan Box of 4: 165 poon Sabado"),
    (_p("Ube", 48), "raise Ube to 48 starting November 2", "itaas ang Ube sa 48 simula Nobyembre 2",
     "ipataas ang Ube sa 48 sugod Nobyembre 2", "pataasa ang Ube sa 48 umpisa Nobyembre 2",
     "pataasa an Ube ha 48 tikang Nobyembre 2", "pataason an Ube sa 48 poon Nobyembre 2"),
    (_p("Puto bumbong", 38), "puto bumbong should be 38 from next Monday on",
     "dapat 38 na ang puto bumbong simula sa Lunes", "dapat 38 na ang puto bumbong sugod sa Lunes",
     "dapat 38 na ang puto bumbong umpisa sa Lunes", "dapat 38 na an puto bumbong tikang ha Lunes",
     "dapat 38 na an puto bumbong poon sa Lunes"),
    (_p("Salted egg", 52), "set salted egg to 52 from Nov 3", "i-set ang salted egg sa 52 simula Nov 3",
     "i-set ang salted egg sa 52 sugod Nov 3", "i-set ang salted egg sa 52 umpisa Nov 3",
     "i-set an salted egg ha 52 tikang Nov 3", "i-set an salted egg sa 52 poon Nov 3"),
    (_p("Cheese overload", 60), "cheese overload will be 60 from Wednesday, permanent",
     "60 na ang cheese overload simula Miyerkules, permanente",
     "60 na ang cheese overload sugod Miyerkules, permanente",
     "60 na ang cheese overload umpisa Miyerkoles, permanente",
     "60 na an cheese overload tikang Miyerkoles, permanente",
     "60 na an cheese overload poon Miyerkoles, permanente"),
    (_p("Classic", 38), "lower the Classic to 38 for good from Friday",
     "ibaba ang Classic sa 38 for good simula Biyernes",
     "ipaubos ang Classic sa 38 for good sugod Biyernes",
     "panubua ang Classic sa 38 for good umpisa Biyernes",
     "paubsa an Classic ha 38 for good tikang Biyernes",
     "pababaon an Classic sa 38 for good poon Biyernes"),
    (_p("Special", 47), "update Special's price to 47 effective Nov 9",
     "i-update ang presyo ng Special sa 47 epektibo Nov 9",
     "i-update ang presyo sa Special sa 47 epektibo Nov 9",
     "i-update ang presyo sang Special sa 47 epektibo Nov 9",
     "i-update an presyo han Special ha 47 epektibo Nov 9",
     "i-update an presyo kan Special sa 47 epektibo Nov 9"),
]  # fmt: skip

SHORT_CODE: list[Row] = [
    ({"item": "Salted egg", "code": "sk"}, "use sk as the short code for salted egg",
     "gawing sk ang code ng salted egg", "himoa nga sk ang code sa salted egg",
     "himua nga sk ang code sang salted egg", "himoa nga sk an code han salted egg",
     "gibohon na sk an code kan salted egg"),
    ({"item": "Cheese overload", "code": "chz"}, "short code for cheese overload: chz",
     "short code ng cheese overload: chz", "short code sa cheese overload: chz",
     "short code sang cheese overload: chz", "short code han cheese overload: chz",
     "short code kan cheese overload: chz"),
    ({"item": "Puto bumbong", "code": "pt"}, "let the clerks type pt for puto bumbong",
     "pwede nang i-type ng clerk ang pt para sa puto bumbong",
     "pwede na i-type sa clerk ang pt para sa puto bumbong",
     "pwede na i-type sang clerk ang pt para sa puto bumbong",
     "puydi na i-type han clerk an pt para ha puto bumbong",
     "pwede nang i-type kan clerk an pt para sa puto bumbong"),
    ({"item": "Kape", "code": "kp"}, "add kp as a code for kape", "idagdag ang kp bilang code ng kape",
     "idugang ang kp isip code sa kape", "idugang ang kp nga code sang kape",
     "idugang an kp sugad nga code han kape", "idagdag an kp bilang code kan kape"),
    ({"item": "Box of 4", "code": "bx4"}, "the code for Box of 4 should be bx4",
     "bx4 dapat ang code ng Box of 4", "bx4 dapat ang code sa Box of 4",
     "bx4 dapat ang code sang Box of 4", "bx4 dapat an code han Box of 4",
     "bx4 dapat an code kan Box of 4"),
    ({"item": "Ube", "code": "ubi"}, "set ubi as the nickname for Ube in the counts",
     "i-set ang ubi bilang palayaw ng Ube sa bilang", "i-set ang ubi isip angga sa Ube sa ihap",
     "i-set ang ubi nga angga sang Ube sa isip", "i-set an ubi sugad nga angga han Ube ha ihap",
     "i-set an ubi bilang palayaw kan Ube sa bilang"),
    ({"item": "Special", "code": "spc"}, "new short code spc for Special",
     "bagong short code na spc para sa Special", "bag-ong short code nga spc para sa Special",
     "bag-o nga short code nga spc para sa Special", "bag-o nga short code nga spc para ha Special",
     "bagong short code na spc para sa Special kan kiosk"),
    ({"item": "Classic", "code": "kl"}, "clerks keep typing kl for Classic, make it a code",
     "lagi tina-type ng clerk ang kl para sa Classic, gawin na nating code",
     "permi i-type sa clerk ang kl para sa Classic, himoa nang code",
     "pirme gina-type sang clerk ang kl para sa Classic, himua na nga code",
     "pirme gin-ta-type han clerk an kl para ha Classic, himoa na nga code",
     "pirmi tina-type kan clerk an kl para sa Classic, gibohon nang code"),
    ({"item": "Cheese overload", "code": "cho"}, "give cheese overload the code cho",
     "bigyan ang cheese overload ng code na cho", "hatagi ang cheese overload og code nga cho",
     "hatagi ang cheese overload sang code nga cho", "hatagi an cheese overload hin code nga cho",
     "tawan an cheese overload nin code na cho"),
    ({"item": "Salted egg", "code": "seg"}, "make seg the short code of salted egg",
     "gawin nating seg ang short code ng salted egg", "himoon nato nga seg ang short code sa salted egg",
     "himuon naton nga seg ang short code sang salted egg",
     "himoon naton nga seg an short code han salted egg",
     "gibohon tang seg an short code kan salted egg"),
]  # fmt: skip

WEEKLY: list[Row] = [
    (NONE, "send me the summary for this week", "pakisend ang summary ngayong linggo",
     "palihug ipadala ang summary karong semanaha", "palihog ipadala ang summary subong nga semana",
     "alayon ipadara an summary yana nga semana", "paki-send an summary ngunyan na semana"),
    (NONE, "weekly report please", "weekly report po", "weekly report palihug",
     "weekly report palihog", "weekly report alayon", "weekly report tabi"),
    (NONE, "how did the branch do this week overall?",
     "kumusta ang branch ngayong linggo sa kabuuan?",
     "kumusta ang branch karong semanaha sa kinatibuk-an?",
     "kamusta ang branch subong nga semana sa kabilugan?",
     "kumusta an branch yana nga semana ha kabug-osan?",
     "kumusta an branch ngunyan na semana sa kabilugan?"),
    (NONE, "what were the best and worst items this week?",
     "ano ang pinakamabenta at pinakamahina ngayong linggo?",
     "unsa ang labing halin ug labing hinay karong semanaha?",
     "ano ang pinakamabaligya kag pinakamahinay subong nga semana?",
     "ano an gimaopay ngan gimaraot nga baligya yana nga semana?",
     "ano an pinakamabenta asin pinakamaluya ngunyan na semana?"),
    (NONE, "give me the week's numbers against target",
     "ibigay ang numbers ng linggo laban sa target", "ihatag ang numbers sa semana batok sa target",
     "ihatag ang numbers sang semana kontra sa target", "ihatag an numbers han semana kontra ha target",
     "itao an numbers kan semana kontra sa target"),
    (NONE, "weekly summary with the waste please", "weekly summary kasama ang nasayang",
     "weekly summary apil ang nausik", "weekly summary upod ang nausik",
     "weekly summary upod an nausik", "weekly summary kaiba an nasayang"),
    (NONE, "recap of last week for the kiosk", "recap ng nakaraang linggo para sa kiosk",
     "recap sa miaging semana para sa kiosk", "recap sang nagligad nga semana para sa kiosk",
     "recap han nakalabay nga semana para ha kiosk", "recap kan nakaaging semana para sa kiosk"),
    (NONE, "end of week report for the branch", "end of week report ng branch",
     "end of week report sa branch", "end of week report sang branch",
     "end of week report han branch", "end of week report kan branch"),
    (NONE, "weekly summary for all branches", "weekly summary ng lahat ng branch",
     "weekly summary sa tanang branch", "weekly summary sang tanan nga branch",
     "weekly summary han ngatanan nga branch", "weekly summary kan gabos na branch"),
    (NONE, "can I see the weekly sales summary now",
     "pwede ko bang makita ang weekly sales summary ngayon",
     "pwede ba nako makita ang weekly sales summary karon",
     "pwede ko bala makita ang weekly sales summary subong",
     "puydi ko ba makita an weekly sales summary yana",
     "pwede ko daw mahiling an weekly sales summary ngunyan"),
]  # fmt: skip

MONTHLY: list[Row] = [
    (NONE, "monthly report please", "buwanang ulat po", "binulan nga report palihug",
     "binulan nga report palihog", "binulan nga report alayon", "binulanang report tabi"),
    (NONE, "the numbers letter for this month", "ang numbers letter ngayong buwan",
     "ang numbers letter karong bulana", "ang numbers letter subong nga bulan",
     "an numbers letter yana nga bulan", "an numbers letter ngunyan na bulan"),
    (NONE, "how did October go? the monthly numbers", "kumusta ang Oktubre? ang monthly numbers",
     "kumusta ang Oktubre? ang binulan nga numbers", "kamusta ang Oktubre? ang numbers sang bulan",
     "kumusta an Oktubre? an numbers han bulan", "kumusta an Oktubre? an numbers kan bulan"),
    (NONE, "month summary: best days, clerks and experiments",
     "summary ng buwan: best days, mga clerk at experiments",
     "summary sa bulan: best days, mga clerk ug experiments",
     "summary sang bulan: best days, mga clerk kag experiments",
     "summary han bulan: best days, mga clerk ngan experiments",
     "summary kan bulan: best days, mga clerk asin experiments"),
    (NONE, "send the monthly letter", "ipadala ang monthly letter", "padad-a ang monthly letter",
     "ipadala ang monthly letter sa akon", "ipadara an monthly letter",
     "ipadara an monthly letter sako"),
    (NONE, "did we hit the month's target? full monthly report",
     "naabot ba natin ang target ng buwan? buong monthly report",
     "naabot ba nato ang target sa bulan? tibuok monthly report",
     "naabot bala naton ang target sang bulan? bilog nga monthly report",
     "naabot ba naton an target han bulan? bug-os nga monthly report",
     "naabot ta daw an target kan bulan? buong monthly report"),
    (NONE, "last month's numbers for the branch", "numbers ng branch noong nakaraang buwan",
     "numbers sa branch sa miaging bulan", "numbers sang branch sang nagligad nga bulan",
     "numbers han branch han nakalabay nga bulan", "numbers kan branch kan nakaaging bulan"),
    (NONE, "monthly sales letter for the kiosk", "buwanang sales letter ng kiosk",
     "binulan nga sales letter sa kiosk", "binulan nga sales letter sang kiosk",
     "binulan nga sales letter han kiosk", "binulanang sales letter kan kiosk"),
    (NONE, "end of month report", "end of month report po", "report sa katapusan sa bulan",
     "report sang katapusan sang bulan", "report han katapusan han bulan",
     "report kan katapusan kan bulan"),
    (NONE, "I need the month's totals per clerk and the best days",
     "kailangan ko ang total ng buwan bawat clerk at ang best days",
     "kinahanglan nako ang total sa bulan matag clerk ug ang best days",
     "kinahanglan ko ang total sang bulan kada clerk kag ang best days",
     "kinahanglan ko an total han bulan kada clerk ngan an best days",
     "kaipuhan ko an total kan bulan kada clerk asin an best days"),
]  # fmt: skip

KEEP_YES, KEEP_NO = {"keep": True}, {"keep": False}
KEEP: list[Row] = [
    (KEEP_YES, "keep it", "ituloy na natin", "padayon na nato", "padayunon na naton",
     "ipadayon na naton", "ipadagos na ta"),
    (KEEP_NO, "go back to the old price", "ibalik sa dati ang presyo", "ibalik sa daan ang presyo",
     "ibalik sa anay nga presyo", "ibalik ha daan nga presyo", "ibalik sa dating presyo"),
    (KEEP_NO, "no, return it to 45", "hindi, ibalik sa 45", "dili, ibalik sa 45",
     "indi, ibalik sa 45", "diri, ibalik ha 45", "dai, ibalik sa 45"),
    (KEEP_YES, "yes, keep 50", "oo, 50 na lang", "oo, ipadayon ang 50", "huo, padayunon ang 50",
     "oo, ipadayon an 50", "iyo, ipadagos an 50"),
    (KEEP_YES, "let's keep the new price for good", "panatilihin na natin ang bagong presyo",
     "ipabilin na nato ang bag-ong presyo", "ipabilin na naton ang bag-o nga presyo",
     "ipabilin na naton an bag-o nga presyo", "padagos na ta an bagong presyo"),
    (KEEP_NO, "the old price was better, revert", "mas okay ang dating presyo, ibalik",
     "mas maayo ang daang presyo, ibalik", "mas maayo ang anay nga presyo, ibalik",
     "mas maupay an daan nga presyo, ibalik", "mas marhay an dating presyo, ibalik"),
    (KEEP_NO, "don't keep it, back to 45", "huwag na, balik sa 45", "ayaw na, balik sa 45",
     "indi na, balik sa 45", "ayaw na, balik ha 45", "dai na, balik sa 45"),
    (KEEP_YES, "good result, stay at 50", "maganda ang resulta, 50 na tayo",
     "nindot ang resulta, 50 na ta", "maayo ang resulta, 50 na kita",
     "maupay an resulta, 50 na kita", "marhay an resulta, 50 na kita"),
    (KEEP_YES, "keep the tested price", "i-keep na ang tested price",
     "i-keep na ang gi-test nga presyo", "i-keep na ang gin-test nga presyo",
     "i-keep na an gin-test nga presyo", "i-keep na an tinest na presyo"),
    (KEEP_NO, "end the test and restore the usual price",
     "tapusin na ang test at ibalik ang dating presyo",
     "tapuson na ang test ug ibalik ang naandan nga presyo",
     "tapuson na ang test kag ibalik ang naandan nga presyo",
     "tapuson na an test ngan ibalik an naandan nga presyo",
     "tapuson na an test asin ibalik an dating presyo"),
]  # fmt: skip

# Mia's experiment result, the message a keep or go-back answer replies to.
RESULT = {
    "en": "The Special test at 50 is done: 12% more pieces and 4% more pesos than usual. Keep 50"
    " or go back to 45?",
    "fil": "Tapos na ang test ng Special sa 50: 12% mas maraming piraso at 4% mas maraming piso"
    " kaysa dati. Ituloy ang 50 o ibalik sa 45?",
    "ceb": "Human na ang test sa Special sa 50: 12% mas daghang buok ug 4% mas daghang piso kaysa"
    " sa naandan. Ipadayon ang 50 o ibalik sa 45?",
    "hil": "Tapos na ang test sang Special sa 50: 12% mas madamo nga buok kag 4% mas madamo nga"
    " piso sang sa naandan. Padayunon ang 50 ukon ibalik sa 45?",
    "war": "Tapos na an test han Special ha 50: 12% mas damo nga buok ngan 4% mas damo nga piso"
    " kay han naandan. Ipadayon an 50 o ibalik ha 45?",
    "bcl": "Tapos na an test kan Special sa 50: 12% mas dakol na piraso asin 4% mas dakol na piso"
    " kaysa dati. Ipadagos an 50 o ibalik sa 45?",
}

# scenario: (expected action, rows)
SEEDS: dict[str, tuple[str, list[Row]]] = {
    "coaching": ("coaching_who", COACHING),
    "how_to_sell": ("how_to_sell", HOW_TO_SELL),
    "experiment_price": ("propose_experiment", EXPERIMENT_PRICE),
    "experiment_promo": ("propose_experiment", EXPERIMENT_PROMO),
    "change_price": ("change_price", CHANGE_PRICE),
    "short_code": ("set_short_code", SHORT_CODE),
    "weekly": ("weekly_summary", WEEKLY),
    "monthly": ("monthly_letter", MONTHLY),
    "keep": ("decide_experiment_result", KEEP),
}
SCENARIOS = tuple(SEEDS)


def _role(scenario: str, seed: int) -> str:
    """Ana asks how to sell; Marites sets short codes, asks most weekly summaries, the last
    four coaching questions and the last two experiments; Rosa the rest."""
    if scenario == "how_to_sell":
        return "clerk"
    late = {"coaching": 6, "experiment_price": 8, "experiment_promo": 8}
    if scenario == "short_code" or (scenario == "weekly" and seed < 8):
        return "supervisor"
    return "supervisor" if seed >= late.get(scenario, 10) else "owner"


CASES: list[Case] = [
    Case(
        lang=lang,
        scenario=scenario,
        text=text,
        expected_action=action,
        role=_role(scenario, i),
        previous=RESULT[lang] if scenario == "keep" else "",
        half="tune" if i % 2 == 0 else "gate",
        expected=expected,
    )
    for scenario, (action, rows) in SEEDS.items()
    for i, (expected, *texts) in enumerate(rows)
    for lang, text in zip(GATED_LANGS, texts, strict=True)
]
