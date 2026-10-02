"""Register the channel adapters this node can use, in every process (server and CLI).

deliver() only queues messages for registered adapters, so every entry point registers the same
set: the simulator always (it stays off unless the organisation enables it) and WhatsApp when
its settings are present.
"""

from mia.channels import registry
from mia.channels.simulator import SimAdapter
from mia.channels.whatsapp import register_if_configured
from mia.settings import Settings


def register_configured(settings: Settings) -> None:
    """Register the simulator and every channel whose settings are configured."""
    registry.register(SimAdapter(on_demand=True))
    register_if_configured(settings)
