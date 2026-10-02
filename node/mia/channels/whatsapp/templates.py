"""Templates approved in WhatsApp Manager. Only templates listed here are ever sent.

Adding a template: create and get it approved in WhatsApp Manager (one per language), then add it
here with the number of body parameters. Quick-reply buttons are part of the approved template,
so they are not sent with the message.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    params: int
    langs: tuple[str, ...]


TEMPLATES: dict[str, Template] = {
    # "Mia: sinulle on uusi viesti työasioista. Vastaa nähdäksesi sen." [Näytä]
    "mia_new_message": Template(params=0, langs=("fi", "en")),
    # "Hei {{1}}, voitko tuurata käynnin {{3}} klo {{4}}, {{2}}?" [Hyväksyn] [En pysty]
    "mia_cover_request": Template(params=4, langs=("fi", "en")),
}
