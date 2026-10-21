"""Templates approved in WhatsApp Manager. Only templates listed here are ever sent.

Adding a template: create and get it approved in WhatsApp Manager (one per language), then add it
here with the number of body parameters. Quick-reply buttons are part of the approved template,
so they are not sent with the message.

`langs` are the languages drafted for each template (texts in docs/whatsapp-setup.md). A language
is sent only once it is also in MIA_WA_TEMPLATE_LANGS (default fi,en): the fil and ceb templates
must be approved in Meta first, then added there.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    params: int
    langs: tuple[str, ...]


TEMPLATES: dict[str, Template] = {
    # "Mia: sinulle on uusi viesti työasioista. Vastaa nähdäksesi sen." [Näytä]
    # fil: "Mia: may bago kang mensahe tungkol sa trabaho. Sumagot para makita ito." [Ipakita]
    # ceb: "Mia: naa kay bag-ong mensahe bahin sa trabaho. Tubaga aron makita kini." [Ipakita]
    "mia_new_message": Template(params=0, langs=("fi", "en", "fil", "ceb")),
    # "Hei {{1}}, voitko tuurata käynnin {{3}} klo {{4}}, {{2}}?" [Hyväksyn] [En pysty]
    # fil: "Hi {{1}}, puwede mo bang i-cover ang pasok sa {{3}} nang {{4}}, {{2}}?"
    # ceb: "Hi {{1}}, mahimo ba nimong i-cover ang duty sa {{3}} sa {{4}}, {{2}}?"
    # (fil and ceb are machine drafts until a native review; buttons in docs/whatsapp-setup.md)
    "mia_cover_request": Template(params=4, langs=("fi", "en", "fil", "ceb")),
    # Authentication template (copy-code button): "Kirjautumiskoodisi on {{1}}. Älä jaa sitä."
    # fil: "Ang sign-in code mo ay {{1}}. Huwag itong ibahagi."
    # ceb: "Ang imong sign-in code kay {{1}}. Ayaw kini ipakigbahin."
    "mia_login_code": Template(params=1, langs=("fi", "en", "fil", "ceb")),
}
