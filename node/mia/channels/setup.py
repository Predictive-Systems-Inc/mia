"""Register the channel adapters this node can use, in every process (server and CLI).

deliver() only queues messages for registered adapters, so every entry point registers the same
set: the simulator in dev mode only (its default webhook secret is public, ADR 021; it stays off
unless the organisation enables it) and WhatsApp when its settings are present.
"""

import logging

from mia.channels import registry
from mia.channels.simulator import SimAdapter
from mia.channels.whatsapp import register_if_configured
from mia.core import orgconfig
from mia.settings import Settings

log = logging.getLogger(__name__)

SIM_DEV_ONLY = "the sim channel runs only with MIA_AUTH_MODE=dev (loopback); ignored on a server"


def register_configured(settings: Settings) -> None:
    """Register every channel whose settings are configured. The simulator is registered only
    in dev mode; in required mode an enabled sim setting is ignored with one warning."""
    if settings.MIA_AUTH_MODE == "dev":
        registry.register(SimAdapter(secret=settings.MIA_SIM_SECRET or None, on_demand=True))
    elif (sim := orgconfig.load().channels.get("sim")) and sim.enabled:
        log.warning("channels.sim.enabled is set: %s", SIM_DEV_ONLY)
    register_if_configured(settings)
