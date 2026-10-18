"""Money and number formatting by language. Amounts are integer minor units (rule 10)."""

FI_GROUP = " "  # narrow no-break space, the Finnish thousands separator
SYMBOLS = {"PHP": "₱", "EUR": "€"}


def format_int(n: int, lang: str) -> str:
    """The integer with the language's thousands separator (a narrow space for fi, else ",")."""
    text = f"{n:,}"
    return text.replace(",", FI_GROUP) if lang == "fi" else text


def format_money(amount: int, currency: str, lang: str) -> str:
    """Minor units as money: "₱1,450.00", "€1,450.00", fi "1 450,00 €", unknown "1,450.00 XXX".

    ponytail: every currency is shown with two decimals; add a minor-unit table for JPY and
    the like when one is used.
    """
    sign = "-" if amount < 0 else ""
    whole, cents = divmod(abs(amount), 100)
    symbol = SYMBOLS.get(currency)
    if lang == "fi":
        number = f"{format_int(whole, lang)},{cents:02d}"
        return f"{sign}{number} {symbol or currency}"
    number = f"{format_int(whole, lang)}.{cents:02d}"
    return f"{sign}{symbol}{number}" if symbol else f"{sign}{number} {currency}"
