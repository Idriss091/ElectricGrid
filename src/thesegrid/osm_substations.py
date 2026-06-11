from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from thesegrid.portfolio_input import PortfolioSite
from thesegrid.substation_identity import normalize_substation_name


DEFAULT_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
OSM_ATTRIBUTION = "© OpenStreetMap contributors, ODbL 1.0"

OsmObjectType = Literal["node", "way", "relation"]
OverpassFetcher = Callable[[str, str], bytes]
Clock = Callable[[], datetime]


class OsmDataAccessError(RuntimeError):
    """Raised when bounded OSM substation discovery cannot be completed."""


class OsmSchemaError(ValueError):
    """Raised when an Overpass response cannot be interpreted safely."""


@dataclass(frozen=True)
class OsmSubstation:
    osm_type: OsmObjectType
    osm_id: int
    latitude: float
    longitude: float
    distance_km: float
    name: str | None
    normalized_name: str
    reference: str | None
    operator: str | None
    operator_is_rte: bool
    voltage_levels_kv: tuple[float, ...]
    source_url: str


@dataclass(frozen=True)
class OsmSourceManifest:
    endpoint: str
    query: str
    client_site_id: str
    radius_km: float
    returned_element_count: int
    returned_candidate_count: int
    retrieved_at_utc: str
    attribution: str


@dataclass(frozen=True)
class OsmSubstationResult:
    substations: tuple[OsmSubstation, ...]
    manifest: OsmSourceManifest


def discover_osm_substations(
    site: PortfolioSite,
    *,
    radius_km: float = 50.0,
    endpoint: str = DEFAULT_OVERPASS_ENDPOINT,
    fetcher: OverpassFetcher | None = None,
    now: Clock | None = None,
) -> OsmSubstationResult:
    if not 1.0 <= radius_km <= 100.0:
        raise ValueError("radius_km must be between 1 and 100")

    query = _build_overpass_query(site, radius_km)
    try:
        payload = (fetcher or _fetch_overpass)(endpoint, query)
    except Exception as exc:
        raise OsmDataAccessError(
            f"failed to retrieve OSM substations for {site.client_site_id}: {exc}"
        ) from exc

    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OsmSchemaError(f"Overpass response is not valid JSON: {exc}") from exc
    elements = document.get("elements")
    if not isinstance(elements, list):
        raise OsmSchemaError("Overpass response is missing an elements list")

    candidates = tuple(
        sorted(
            filter(
                None,
                (_parse_candidate(element, site) for element in elements),
            ),
            key=lambda candidate: (
                candidate.distance_km,
                candidate.osm_type,
                candidate.osm_id,
            ),
        )
    )
    retrieved_at = (now or _utc_now)()
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    retrieved_at = retrieved_at.astimezone(UTC)
    return OsmSubstationResult(
        substations=candidates,
        manifest=OsmSourceManifest(
            endpoint=endpoint,
            query=query,
            client_site_id=site.client_site_id,
            radius_km=radius_km,
            returned_element_count=len(elements),
            returned_candidate_count=len(candidates),
            retrieved_at_utc=retrieved_at.isoformat(),
            attribution=OSM_ATTRIBUTION,
        ),
    )


def parse_osm_voltage_levels_kv(value: object) -> tuple[float, ...]:
    text = str(value).replace(",", ".")
    explicit_kv_unit = re.search(r"\bkv\b", text, re.IGNORECASE) is not None
    levels: set[float] = set()
    for raw_number in re.findall(r"\d+(?:\.\d+)?", text):
        number = float(raw_number)
        if number <= 0.0:
            continue
        level_kv = number if explicit_kv_unit else number / 1000.0
        levels.add(round(level_kv, 3))
    return tuple(sorted(levels))


def haversine_distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    earth_radius_km = 6371.0088
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * earth_radius_km * math.asin(math.sqrt(haversine))


def _build_overpass_query(site: PortfolioSite, radius_km: float) -> str:
    radius_m = int(round(radius_km * 1000.0))
    return (
        "[out:json][timeout:25];"
        f'(nwr["power"="substation"]'
        f"(around:{radius_m},{site.latitude:g},{site.longitude:g}););"
        "out center tags;"
    )


def _parse_candidate(
    element: object,
    site: PortfolioSite,
) -> OsmSubstation | None:
    if not isinstance(element, dict):
        return None
    osm_type = element.get("type")
    if osm_type not in {"node", "way", "relation"}:
        return None
    osm_id = element.get("id")
    if not isinstance(osm_id, int):
        return None
    tags = element.get("tags", {})
    if not isinstance(tags, dict) or tags.get("power") != "substation":
        return None

    latitude, longitude = _element_coordinates(element)
    if latitude is None or longitude is None:
        return None
    operator = _optional_text(tags.get("operator"))
    operator_is_rte = _is_rte_operator(operator, tags.get("operator:wikidata"))
    voltage_levels = parse_osm_voltage_levels_kv(tags.get("voltage", ""))
    if not operator_is_rte and not any(level >= 63.0 for level in voltage_levels):
        return None

    name = _optional_text(tags.get("name"))
    return OsmSubstation(
        osm_type=osm_type,
        osm_id=osm_id,
        latitude=latitude,
        longitude=longitude,
        distance_km=haversine_distance_km(
            site.latitude,
            site.longitude,
            latitude,
            longitude,
        ),
        name=name,
        normalized_name="" if name is None else normalize_substation_name(name),
        reference=_optional_text(tags.get("ref")),
        operator=operator,
        operator_is_rte=operator_is_rte,
        voltage_levels_kv=voltage_levels,
        source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
    )


def _element_coordinates(element: dict[str, object]) -> tuple[float | None, float | None]:
    if element.get("type") == "node":
        latitude = element.get("lat")
        longitude = element.get("lon")
    else:
        center = element.get("center")
        if not isinstance(center, dict):
            return None, None
        latitude = center.get("lat")
        longitude = center.get("lon")
    if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
        return None, None
    return float(latitude), float(longitude)


def _is_rte_operator(operator: str | None, wikidata: object) -> bool:
    if str(wikidata).strip() == "Q2178795":
        return True
    if operator is None:
        return False
    normalized = normalize_substation_name(operator)
    return normalized == "RTE" or "RESEAUDETRANSPORTDELECTRICITE" in normalized


def _fetch_overpass(endpoint: str, query: str) -> bytes:
    request = Request(
        endpoint,
        data=urlencode({"data": query}).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "VoltPath/0.1 portfolio-screening contact=local-operator",
        },
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return response.read()


def _optional_text(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def _utc_now() -> datetime:
    return datetime.now(UTC)
