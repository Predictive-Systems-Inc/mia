"""The bookkeeper's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store. None yet; each new tool is a manifest entry plus a binding here."""

from mia.agents.base import ToolBinding

BINDINGS: list[ToolBinding] = []
