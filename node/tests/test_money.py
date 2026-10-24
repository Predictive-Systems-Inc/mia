from mia.core.money import format_int, format_money


def test_php_and_eur() -> None:
    assert format_money(145000, "PHP", "fil") == "₱1,450.00"
    assert format_money(145000, "EUR", "fi") == "1 450,00 €"
    assert format_money(145000, "EUR", "en") == "€1,450.00"
    assert format_money(5, "XXX", "en") == "0.05 XXX"


def test_negative_and_large_amounts() -> None:
    assert format_money(-123456789, "PHP", "en") == "-₱1,234,567.89"


def test_int_by_language() -> None:
    assert format_int(1450, "en") == "1,450"
    assert format_int(1450, "fi") == "1 450"
    assert format_int(1450, "ceb") == "1,450"
