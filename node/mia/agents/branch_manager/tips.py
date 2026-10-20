"""Seed data only: the curated tips, quotes and pricing strategies of the branch manager.

The retail seed writes these into branch_manager_tips and branch_manager_strategies. Every row
names its source: the shop's own line ("Ferino's house line") or a public-domain work (Q75).
No code reads this module at run time; the agent reads the tables.
"""

from typing import Any

HOUSE = "Ferino's house line"
SALAWIKAIN = "Filipino proverb (salawikain), public domain"
FRANKLIN = "Benjamin Franklin, Poor Richard's Almanack (1730s to 1750s), public domain"
AESOP = "Aesop's Fables, public domain"
KARTILYA = "Emilio Jacinto, Kartilya ng Katipunan (1896), public domain"

# item name (None for a general tip), Filipino, English, source
TIPS: list[tuple[str | None, str, str, str]] = [
    (
        None,
        "Batiin muna ang bawat customer nang nakangiti, bago pa sila magtanong.",
        "Greet every customer first, with a smile, before they ask.",
        HOUSE,
    ),
    (
        None,
        "Banggitin ang pinakamabenta ngayong araw kapag may tumitingin sa menu.",
        "Name today's best seller when someone is looking at the menu.",
        HOUSE,
    ),
    (
        None,
        "Mag-alok ng kape sa bawat order; marami ang pumapayag kapag inalok.",
        "Offer a coffee with every order; many say yes when asked.",
        HOUSE,
    ),
    (
        None,
        "Panatilihing puno at mainit ang display; mas matumal ang tray na kalahati lang ang laman.",
        "Keep the display full and warm; a half-empty tray sells less.",
        HOUSE,
    ),
    (
        None,
        "Pasalamatan ang bawat customer at imbitahang bumalik bukas.",
        "Thank every customer and invite them back tomorrow.",
        HOUSE,
    ),
    (
        None,
        "Imungkahi ang box kapag pang-pamilya ang binibili ng customer.",
        "Suggest the box when a customer is buying for a family.",
        HOUSE,
    ),
    (
        None,
        "Iabot ang order gamit ang dalawang kamay at sabihin kung ano ang laman.",
        "Hand over the order with both hands and say what is inside.",
        HOUSE,
    ),
    (
        None,
        "Kapag mahaba ang pila, batiin ang mga naghihintay para hindi sila umalis.",
        "When the line is long, greet the people waiting so they stay.",
        HOUSE,
    ),
    (
        None,
        (
            "Hayaang maamoy ng nag-aalangang customer ang bagong lutong bibingka; ang bango ang "
            "nagbebenta."
        ),
        "Let a hesitant customer smell the fresh bibingka; the aroma sells.",
        HOUSE,
    ),
    (
        None,
        "Bilangin ang benta bago magsara para tama ang bilang sa pagsisimula bukas.",
        "Count your sales before closing so tomorrow starts with the right numbers.",
        HOUSE,
    ),
    (
        "Classic",
        "Sabihin sa unang beses bumili na ang classic ang orihinal na recipe ng tindahan.",
        "Tell first-time buyers that the classic is the recipe the shop started with.",
        HOUSE,
    ),
    (
        "Classic",
        "Ihain ang classic nang mainit mula sa palayok at sabihing bagong luto ito.",
        "Serve the classic hot from the clay pot and say it is freshly baked.",
        HOUSE,
    ),
    (
        "Classic",
        "Ipares ang classic sa kape para sa mga bumibili sa umaga.",
        "Pair the classic with a coffee for the morning crowd.",
        HOUSE,
    ),
    (
        "Classic",
        "Kapag may natitirang classic sa hapon, ialok muna sa mga suki.",
        "When classics are left late in the day, offer them to the regulars first.",
        HOUSE,
    ),
    (
        "Puto bumbong",
        "Ipaalala sa customer na paborito tuwing Pasko ang puto bumbong, at mayroon na ngayon.",
        "Remind customers that puto bumbong is a Christmas favourite, and it is here now.",
        HOUSE,
    ),
    (
        "Puto bumbong",
        "Itanong kung gusto nila ng dagdag na margarina at niyog sa puto bumbong.",
        "Ask if they would like extra margarine and grated coconut on the puto bumbong.",
        HOUSE,
    ),
    (
        "Puto bumbong",
        "Ilagay ang puto bumbong kung saan kita ang kulay-ube nito sa counter.",
        "Put the puto bumbong where its purple colour shows on the counter.",
        HOUSE,
    ),
    (
        "Salted egg",
        "Sabihin na may hiwa ng tunay na itlog na maalat sa ibabaw ng salted egg bibingka.",
        "Tell customers the salted egg bibingka has a slice of real salted egg on top.",
        HOUSE,
    ),
    (
        "Salted egg",
        "Ialok ang salted egg sa mga mahilig sa lasang maalat-matamis.",
        "Offer the salted egg to customers who like a salty-sweet taste.",
        HOUSE,
    ),
    (
        "Salted egg",
        "Imungkahi ang isang salted egg at isang classic sa mga hindi makapili.",
        "Suggest one salted egg and one classic to customers who cannot choose.",
        HOUSE,
    ),
]

# Filipino, English, source
QUOTES: list[tuple[str, str, str]] = [
    (
        "Ang hindi lumingon sa pinanggalingan ay hindi makararating sa paroroonan.",
        "One who does not look back to where they came from will not reach where they are going.",
        SALAWIKAIN,
    ),
    ("Kapag may itinanim, may aanihin.", "What you plant, you will harvest.", SALAWIKAIN),
    ("Pag may tiyaga, may nilaga.", "With patience, there is food on the table.", SALAWIKAIN),
    (
        (
            "Ang lumakad nang matulin, kung matinik ay malalim; ang lumakad nang marahan, matinik man "
            "ay mababaw."
        ),
        (
            "Who walks fast and steps on a thorn is pricked deep; who walks slowly is pricked only "
            "lightly."
        ),
        SALAWIKAIN,
    ),
    (
        "Ang pagsasabi ng tapat ay pagsasama nang maluwag.",
        "Telling the truth makes working together easy.",
        SALAWIKAIN,
    ),
    (
        "Walang mahirap na gawa kapag dinaan sa tiyaga.",
        "No work is hard when it is done with patience.",
        SALAWIKAIN,
    ),
    (
        "Habang maikli ang kumot, matutong mamaluktot.",
        "While the blanket is short, learn to curl up.",
        SALAWIKAIN,
    ),
    ("Nasa Diyos ang awa, nasa tao ang gawa.", "Mercy is God's, the work is ours.", SALAWIKAIN),
    (
        "Ang sakit ng kalingkingan, ramdam ng buong katawan.",
        "The pain of the little finger is felt by the whole body.",
        SALAWIKAIN,
    ),
    ("Kung ano ang puno, siya ang bunga.", "As the tree is, so is its fruit.", SALAWIKAIN),
    (
        "Mas mabuti ang mahusay na nagawa kaysa sa mahusay na nasabi.",
        "Well done is better than well said.",
        FRANKLIN,
    ),
    ("Ang sipag ang ina ng suwerte.", "Diligence is the mother of good luck.", FRANKLIN),
    (
        "Ang nasayang na oras ay hindi na muling matatagpuan.",
        "Lost time is never found again.",
        FRANKLIN,
    ),
    (
        "Ang mabagal pero tuloy-tuloy ang nananalo sa karera.",
        "Slow and steady wins the race.",
        f"{AESOP} (The Tortoise and the Hare)",
    ),
    (
        "Paunti-unti, nagagawa rin.",
        "Little by little does the trick.",
        f"{AESOP} (The Crow and the Pitcher)",
    ),
    (
        "Ang ayaw mong gawin sa iyo, huwag mong gawin sa iba.",
        "What you do not want done to yourself, do not do to others.",
        "Confucius, Analects 15.24 (James Legge translation, 1861), public domain",
    ),
    (
        "Ang paglalakbay na sanlibong milya ay nagsisimula sa isang hakbang.",
        "A journey of a thousand miles begins with a single step.",
        "Laozi, Tao Te Ching, chapter 64, public domain",
    ),
    (
        "Huwag nang mag-aksaya ng oras sa pagtatalo kung ano ang mabuting tao. Maging isa ka.",
        "Waste no more time arguing what a good man should be. Be one.",
        "Marcus Aurelius, Meditations 10.16, public domain",
    ),
    (
        "Sa taong may hiya, salita'y panunumpa.",
        "To a person of honour, a word is an oath.",
        KARTILYA,
    ),
    (
        (
            "Huwag mong sasayangin ang panahon; ang yamang nawala'y magyayaring magbalik, nguni't "
            "panahong nagdaan na'y di na muli pang magdadaan."
        ),
        "Do not waste time; lost riches may come back, but time gone by will never return.",
        KARTILYA,
    ),
]

NAGLE = "Nagle and Muller, The Strategy and Tactics of Pricing"
# name_key, kind (the experiment kind), params (read by experiments.py), source, description (the
# fixed English line Jev reads to match a request, actions.build_query); spec section 13.
# Money in params is minor units, shares and cuts are whole percents.
STRATEGIES: list[tuple[str, str, dict[str, Any], str, str]] = [
    (
        "bm.strategy.charm",
        "price",
        {"endings": [0], "under": 100},  # 50 pesos tested at 49
        (
            "Thomas and Morwitz, Penny Wise and Pound Foolish: The Left-Digit Effect in Price "
            "Cognition (2005)"
        ),
        "Charm pricing: a price just under a round number (49 instead of 50)",
    ),
    (
        "bm.strategy.anchor",
        "price",
        {"premium_percent": 20},
        f"Tversky and Kahneman, Judgment under Uncertainty (1974), on anchoring; {NAGLE}",
        "Anchoring: a premium item or price shown next to the usual one",
    ),
    (
        "bm.strategy.bundle",
        "bundle",
        {"off_percent": 10, "min_pair_share": 30},
        "Stremersch and Tellis, Strategic Bundling of Products and Prices (2002)",
        "Bundling: items often bought together sold as one, a little cheaper",
    ),
    (
        "bm.strategy.volume",
        "promo",
        {"min_quantity": 3, "off_percent": 10, "min_multi_share": 30},
        f"{NAGLE} (nonlinear pricing)",
        "Volume pricing: less per piece when buying several (3 for, buy more)",
    ),
    (
        "bm.strategy.markdown",
        "promo",
        {"min_leftover_days": 2, "window_days": 14, "max_off_percent": 20},
        "Talluri and van Ryzin, The Theory and Practice of Revenue Management (2004)",
        "Markdown: a lower price for an item usually left over at closing",
    ),
    (
        "bm.strategy.increase",
        "price",
        {"min_sold_out_share": 50, "up_percent_min": 5, "up_percent_max": 10},
        "Simon and Fassnacht, Price Management (2019), elasticity testing",
        "A price increase for an item that often sells out",
    ),
    (
        "bm.strategy.seasonal",
        "promo",
        {"lead_days": 14},
        "The shop's own history: last year's sales of the same month",
        "A seasonal promo before a holiday or a busy month",
    ),
    (
        "bm.strategy.decoy",
        "price",
        {"variants": 3},
        f"Ariely, Predictably Irrational (2008); {NAGLE}",
        "Decoy pricing: three sizes or variants so the middle one looks best",
    ),
]
