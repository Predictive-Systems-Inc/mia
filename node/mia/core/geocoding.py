"""Geocoding: addresses to coordinates, behind one interface with pluggable providers.

Guarantees: every lookup checks geocode_cache first, so an address leaves the node at most once
per provider; network lookups go only through the egress transport (blocked at level `none`,
logged in egress_log); results are written through mia.core.store with an event. Providers are
chosen by name in settings (MIA_GEOCODER), so adding a country means adding a provider, not
changing callers.
"""

from collections.abc import Callable
from typing import Protocol

import httpx
from pydantic import BaseModel
from sqlmodel import Session, col, select

from mia.core import store
from mia.core.egress import EgressContext, EgressTransport, egress_context
from mia.core.models import Actor, Branch, GeocodeCache, Location, Person
from mia.settings import Settings, get_settings


class GeoPoint(BaseModel):
    lat: float
    lon: float
    label: str = ""


class GeocodingError(Exception):
    """The provider could not be used (missing key, HTTP error)."""


class GeocodeProvider(Protocol):
    name: str

    async def geocode(self, address: str) -> GeoPoint | None:
        """Best match for the address, or None when nothing matches."""
        ...


class StaticProvider:
    """Offline provider with a fixed table. Used by tests and air-gapped demos."""

    name = "static"

    def __init__(self, table: dict[str, GeoPoint] | None = None) -> None:
        self.table = {k.strip().lower(): v for k, v in (table or {}).items()}

    async def geocode(self, address: str) -> GeoPoint | None:
        return self.table.get(address.strip().lower())


class DigitransitProvider:
    """Digitransit geocoding (Finland). https://digitransit.fi/en/developers/apis/3-geocoding-api/"""

    name = "digitransit"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.digitransit.fi/geocoding/v1",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise GeocodingError("MIA_GEOCODER_KEY is required for the digitransit provider")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = EgressTransport(transport, pseudonymise=False, meter=False)

    async def geocode(self, address: str) -> GeoPoint | None:
        headers = {"digitransit-subscription-key": self.api_key}
        params = {"text": address, "size": "1", "lang": "fi"}
        async with httpx.AsyncClient(transport=self.transport, timeout=15) as client:
            response = await client.get(f"{self.base_url}/search", params=params, headers=headers)
        if response.status_code >= 400:
            raise GeocodingError(f"digitransit returned HTTP {response.status_code}")
        features = response.json().get("features") or []
        if not features:
            return None
        lon, lat = features[0]["geometry"]["coordinates"][:2]
        label = str(features[0].get("properties", {}).get("label", ""))
        return GeoPoint(lat=float(lat), lon=float(lon), label=label)


ProviderFactory = Callable[[Settings], GeocodeProvider]
_providers: dict[str, ProviderFactory] = {
    "static": lambda s: StaticProvider(),
    "digitransit": lambda s: DigitransitProvider(s.MIA_GEOCODER_KEY, s.MIA_GEOCODER_URL),
}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Add a provider (for example one for the Philippines) without changing callers."""
    _providers[name] = factory


def get_provider(settings: Settings | None = None) -> GeocodeProvider:
    settings = settings or get_settings()
    if settings.MIA_GEOCODER not in _providers:
        raise GeocodingError(f"unknown geocoder {settings.MIA_GEOCODER!r}")
    return _providers[settings.MIA_GEOCODER](settings)


def _normalise(address: str) -> str:
    return " ".join(address.split()).lower()


def cached(session: Session, branch_id: str, address: str) -> GeoPoint | None:
    """A previous result for this address from any provider, if there is one."""
    key = _normalise(address)
    rows = session.exec(
        select(GeocodeCache)
        .where(GeocodeCache.branch_id == branch_id)
        .order_by(col(GeocodeCache.id))
    ).all()
    for row in rows:
        if _normalise(row.address) == key:
            return GeoPoint(lat=row.lat, lon=row.lon, label=row.label)
    return None


async def geocode(
    session: Session, address: str, actor: Actor, provider: GeocodeProvider | None = None
) -> GeoPoint | None:
    """Coordinates for an address: cache first, then the provider through egress."""
    if not address.strip():
        return None
    hit = cached(session, actor.branch_id, address)
    if hit is not None:
        return hit
    provider = provider or get_provider()
    branch = session.get(Branch, actor.branch_id)
    ctx = EgressContext(
        session=session,
        actor=actor,
        organisation_id=branch.organisation_id if branch else "",
        agent_id="core.geocoding",
        purpose="geocoding",
        level=get_settings().MIA_EGRESS_LEVEL,
        provider=provider.name,
    )
    with egress_context(ctx):
        point = await provider.geocode(address)
    if point is not None:
        row = GeocodeCache(
            branch_id=actor.branch_id,
            address=address,
            provider=provider.name,
            lat=point.lat,
            lon=point.lon,
            label=point.label,
        )
        store.insert(session, row, actor, action="geocode.cached")
    return point


async def fill_missing(
    session: Session, actor: Actor, provider: GeocodeProvider | None = None
) -> tuple[int, list[str]]:
    """Geocode home bases and sites that have an address but no coordinates.

    Returns (rows updated, addresses that could not be geocoded).
    """
    updated, missing = 0, []
    persons = session.exec(
        select(Person).where(Person.branch_id == actor.branch_id).where(Person.home_lat == None)
    ).all()
    for person in persons:
        if not person.home_address:
            continue
        point = await geocode(session, person.home_address, actor, provider)
        if point is None:
            missing.append(person.home_address)
            continue
        store.update(session, person, {"home_lat": point.lat, "home_lon": point.lon}, actor)
        updated += 1
    locations = session.exec(
        select(Location).where(Location.branch_id == actor.branch_id).where(Location.lat == None)
    ).all()
    for loc in locations:
        point = await geocode(session, loc.address, actor, provider)
        if point is None:
            missing.append(loc.address)
            continue
        store.update(session, loc, {"lat": point.lat, "lon": point.lon}, actor)
        updated += 1
    return updated, missing
