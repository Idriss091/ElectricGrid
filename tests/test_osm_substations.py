from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from thesegrid.osm_substations import (
    OsmDataAccessError,
    discover_osm_substations,
    haversine_distance_km,
    parse_osm_voltage_levels_kv,
)
from thesegrid.portfolio_input import PortfolioSite


def _site() -> PortfolioSite:
    return PortfolioSite(
        client_site_id="SITE-01",
        latitude=48.85,
        longitude=2.35,
        requested_mw=100.0,
        storage_duration_hours=2.0,
    )


def test_discover_osm_substations_builds_bounded_query_and_filters_candidates():
    captured: dict[str, str] = {}
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 101,
                "lat": 48.86,
                "lon": 2.36,
                "tags": {
                    "power": "substation",
                    "name": "Poste Alpha",
                    "operator": "RTE",
                    "ref": ".ALPH",
                    "voltage": "225000;63000",
                },
            },
            {
                "type": "way",
                "id": 202,
                "center": {"lat": 48.87, "lon": 2.37},
                "tags": {
                    "power": "substation",
                    "name": "Poste Beta",
                    "operator": "Enedis",
                    "voltage": "90000",
                },
            },
            {
                "type": "relation",
                "id": 303,
                "center": {"lat": 48.88, "lon": 2.38},
                "tags": {
                    "power": "substation",
                    "name": "Distribution locale",
                    "operator": "Enedis",
                    "voltage": "20000",
                },
            },
        ]
    }

    def fetcher(endpoint: str, query: str) -> bytes:
        captured["endpoint"] = endpoint
        captured["query"] = query
        return json.dumps(payload).encode()

    result = discover_osm_substations(
        _site(),
        radius_km=35.0,
        endpoint="https://overpass.test/api/interpreter",
        fetcher=fetcher,
        now=lambda: datetime(2026, 6, 11, 10, 0, tzinfo=UTC),
    )

    assert captured["endpoint"] == "https://overpass.test/api/interpreter"
    assert 'nwr["power"="substation"](around:35000,48.85,2.35)' in captured["query"]
    assert [candidate.osm_id for candidate in result.substations] == [101, 202]
    assert result.substations[0].voltage_levels_kv == (63.0, 225.0)
    assert result.substations[0].source_url == "https://www.openstreetmap.org/node/101"
    assert result.substations[1].latitude == pytest.approx(48.87)
    assert result.manifest.radius_km == pytest.approx(35.0)
    assert result.manifest.returned_candidate_count == 2
    assert result.manifest.retrieved_at_utc == "2026-06-11T10:00:00+00:00"
    assert "OpenStreetMap contributors" in result.manifest.attribution


def test_discover_osm_substations_retains_rte_candidate_without_voltage():
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 48.851,
                "lon": 2.351,
                "tags": {
                    "power": "substation",
                    "operator": "Réseau de Transport d'Électricité",
                },
            }
        ]
    }

    result = discover_osm_substations(
        _site(),
        fetcher=lambda _endpoint, _query: json.dumps(payload).encode(),
    )

    assert len(result.substations) == 1
    assert result.substations[0].operator_is_rte is True
    assert result.substations[0].voltage_levels_kv == ()


def test_discover_osm_substations_rejects_unbounded_radius_and_source_failures():
    with pytest.raises(ValueError, match="radius_km must be between 1 and 100"):
        discover_osm_substations(_site(), radius_km=101)

    def failed_fetcher(_endpoint: str, _query: str) -> bytes:
        raise TimeoutError("timed out")

    with pytest.raises(OsmDataAccessError, match="timed out"):
        discover_osm_substations(_site(), fetcher=failed_fetcher)


def test_parse_osm_voltage_levels_kv_handles_osm_voltage_formats():
    assert parse_osm_voltage_levels_kv("225000; 63000") == (63.0, 225.0)
    assert parse_osm_voltage_levels_kv("90 kV / 20 kV") == (20.0, 90.0)
    assert parse_osm_voltage_levels_kv("400") == (0.4,)
    assert parse_osm_voltage_levels_kv("") == ()


def test_haversine_distance_is_zero_for_same_point_and_symmetric():
    assert haversine_distance_km(48.85, 2.35, 48.85, 2.35) == pytest.approx(0.0)
    forward = haversine_distance_km(48.85, 2.35, 48.95, 2.45)
    backward = haversine_distance_km(48.95, 2.45, 48.85, 2.35)

    assert forward == pytest.approx(backward)
    assert forward == pytest.approx(13.31, rel=0.02)
