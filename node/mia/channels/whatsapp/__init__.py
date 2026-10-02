"""WhatsApp channel (Meta Cloud API). See docs/whatsapp-setup.md."""

from mia.channels import registry
from mia.settings import Settings


def register_if_configured(settings: Settings) -> bool:
    """Register the WhatsApp adapter when its token, app secret and number id are set."""
    if not (
        settings.MIA_WA_TOKEN and settings.MIA_WA_APP_SECRET and settings.MIA_WA_PHONE_NUMBER_ID
    ):
        return False
    from mia.channels.whatsapp.adapter import WhatsAppAdapter

    registry.register(WhatsAppAdapter(settings))
    return True
