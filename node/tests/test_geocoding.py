"""Geocoding: pluggable providers, cache, and egress (D7)."""

import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlmodel import Session, select

from mia.core import geocoding
from mia.core.egress import EgressBlocked
from mia.core.geocoding import DigitransitProvider, GeocodingError, GeoPoint, StaticProvider
from mia.core.models import Actor, EgressLog, GeocodeCache, Location, Person, UsageCloudRequest
from mia.settings import get_settings

ADDRESS = "Mikaelinkatu 1, 00100 Helsinki"


def digitransit_reply(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        feature = {
            "geometry": {"coordinates": [24.95, 60.17]},
            "properties": {"label": "Mikaelinkatu 1, Helsinki"},
        }
        return httpx.Response(200, json={"features": [feature]})

    return httpx.MockTransport(handler)


def test_digitransit_goes_through_egress_and_is_cached(
    session: Session, people: dict[str, Person]
) -> None:
    seen: list[httpx.Request] = []
    provider = DigitransitProvider("key-1", transport=digitransit_reply(seen))
    actor = Actor.person(people["Sanna"])
    point = asyncio.run(geocoding.geocode(session, ADDRESS, actor, provider))
    assert point == GeoPoint(lat=60.17, lon=24.95, label="Mikaelinkatu 1, Helsinki")
    query = parse_qs(urlparse(str(seen[0].url)).query)
    assert query["text"] == [ADDRESS]  # addresses leave as they are, not pseudonymised
    assert seen[0].headers["digitransit-subscription-key"] == "key-1"
    log = session.exec(select(EgressLog)).one()
    assert (log.purpose, log.provider, log.agent_id) == (
        "geocoding",
        "digitransit",
        "core.geocoding",
    )
    assert session.exec(select(UsageCloudRequest)).all() == []  # not a model call

    again = asyncio.run(
        geocoding.geocode(session, "  mikaelinkatu 1,  00100 helsinki ", actor, provider)
    )
    assert again is not None and again.lat == 60.17 and len(seen) == 1  # served from the cache


def test_level_none_blocks_geocoding(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIA_EGRESS_LEVEL", "none")
    get_settings.cache_clear()
    seen: list[httpx.Request] = []
    provider = DigitransitProvider("key-1", transport=digitransit_reply(seen))
    with pytest.raises(EgressBlocked):
        asyncio.run(geocoding.geocode(session, ADDRESS, Actor.person(people["Sanna"]), provider))
    assert seen == []


def test_provider_errors_and_no_match(session: Session, people: dict[str, Person]) -> None:
    with pytest.raises(GeocodingError, match="MIA_GEOCODER_KEY"):
        DigitransitProvider("")
    empty = httpx.MockTransport(lambda r: httpx.Response(200, json={"features": []}))
    actor = Actor.person(people["Sanna"])
    assert (
        asyncio.run(
            geocoding.geocode(
                session, "Nowhere 1", actor, DigitransitProvider("k", transport=empty)
            )
        )
        is None
    )
    failing = httpx.MockTransport(lambda r: httpx.Response(503))
    with pytest.raises(GeocodingError, match="503"):
        asyncio.run(
            geocoding.geocode(
                session, "Elsewhere 2", actor, DigitransitProvider("k", transport=failing)
            )
        )
    assert asyncio.run(geocoding.geocode(session, "   ", actor, StaticProvider())) is None


def test_providers_are_pluggable() -> None:
    settings = get_settings()
    assert isinstance(
        geocoding.get_provider(settings), StaticProvider
    )  # tests use MIA_GEOCODER=static
    geocoding.register_provider("fixed", lambda s: StaticProvider({"a": GeoPoint(lat=1, lon=2)}))
    assert isinstance(
        geocoding.get_provider(settings.model_copy(update={"MIA_GEOCODER": "fixed"})),
        StaticProvider,
    )
    with pytest.raises(GeocodingError, match="unknown geocoder"):
        geocoding.get_provider(settings.model_copy(update={"MIA_GEOCODER": "nope"}))
    digi = geocoding.get_provider(
        settings.model_copy(update={"MIA_GEOCODER": "digitransit", "MIA_GEOCODER_KEY": "k"})
    )
    assert digi.name == "digitransit"


def test_fill_missing_updates_people_and_sites(session: Session, people: dict[str, Person]) -> None:
    actor = Actor.system(people["Juha"].branch_id)
    aino = people["Aino"]
    aino.home_lat = aino.home_lon = None
    aino.home_address = "Uusi katu 1"
    session.add(aino)
    site = session.exec(select(Location)).first()
    assert site is not None
    site.lat = site.lon = None
    site.address = "Uusi katu 2"
    session.add(site)
    session.flush()
    provider = StaticProvider({"Uusi katu 1": GeoPoint(lat=60.2, lon=24.9)})
    updated, missing = asyncio.run(geocoding.fill_missing(session, actor, provider))
    assert updated == 1 and missing == ["Uusi katu 2"]
    session.refresh(aino)
    assert (aino.home_lat, aino.home_lon) == (60.2, 24.9)
    assert session.exec(select(GeocodeCache).where(GeocodeCache.provider == "static")).one()
