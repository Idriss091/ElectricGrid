from __future__ import annotations

import csv
import json
from datetime import UTC, datetime

from thesegrid.osm_substations import OsmSourceManifest, OsmSubstation
from thesegrid.portfolio_input import PortfolioSite
from thesegrid.portfolio_reporting import write_portfolio_screening_outputs
from thesegrid.portfolio_screening import screen_portfolio
from thesegrid.substation_identity import (
    CartostockSubstation,
    FrenchSubstationIdentity,
    OsmSubstationIdentityLink,
)


def _screening_result():
    site = PortfolioSite(
        client_site_id="SITE-CLIENT-01",
        latitude=48.85,
        longitude=2.35,
        requested_mw=50.0,
        storage_duration_hours=2.0,
        land_control_status="secured",
        target_connection_date="2028-09-30",
        preferred_voltage_kv=225.0,
    )
    substation = OsmSubstation(
        osm_type="way",
        osm_id=101,
        latitude=48.86,
        longitude=2.36,
        distance_km=1.33,
        name="Alpha",
        normalized_name="ALPHA",
        reference=".ALPH",
        operator="RTE",
        operator_is_rte=True,
        voltage_levels_kv=(63.0, 225.0),
        source_url="https://www.openstreetmap.org/way/101",
    )
    identity = FrenchSubstationIdentity(
        cartostock_id="ALPHA7",
        cartostock_station_name="ALPHA",
        normalized_name="ALPHA",
        voltage_kv=225.0,
        commune_insee_code="75056",
        commune_name="Paris",
        odre_code=".ALPH",
        odre_name="ALPHA",
        rte7000_id=".ALPH",
        match_confidence="exact",
        match_method="normalized_name_and_voltage",
        candidate_count=1,
        manual_review_required=False,
    )
    link = OsmSubstationIdentityLink(
        substation=substation,
        identity=identity,
        match_confidence="exact",
        match_method="odre_code",
        candidate_count=1,
        manual_review_required=False,
    )
    cartostock = CartostockSubstation(
        cartostock_id="ALPHA7",
        address_label="POSTE 225kV N0 1 ALPHA",
        station_name="ALPHA",
        normalized_name="ALPHA",
        voltage_kv=225.0,
        commune_insee_code="75056",
        commune_name="Paris",
        nearby_demand=None,
        capacity_without_constraint="< 5 MW",
        turpe_zone="zone soutirage",
        injection_period=None,
        gabarit="gabarit en injection",
        gabarit_substation_capacity="100 MW",
        gabarit_zone_name="Alpha",
        gabarit_zone_capacity="55 MW",
    )
    return screen_portfolio(
        (site,),
        {"SITE-CLIENT-01": (link,)},
        (cartostock,),
    )


def test_write_portfolio_screening_outputs_creates_complete_client_bundle(tmp_path):
    result = _screening_result()
    source_manifest = OsmSourceManifest(
        endpoint="https://overpass.test/api/interpreter",
        query="[out:json];...",
        client_site_id="SITE-CLIENT-01",
        radius_km=50.0,
        returned_element_count=4,
        returned_candidate_count=1,
        retrieved_at_utc="2026-06-11T10:00:00+00:00",
        attribution="© OpenStreetMap contributors, ODbL 1.0",
    )

    outputs = write_portfolio_screening_outputs(
        result,
        tmp_path,
        source_manifests=(source_manifest,),
        now=lambda: datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
    )

    assert outputs.ranked_csv_path.exists()
    assert outputs.candidates_csv_path.exists()
    assert outputs.report_path.exists()
    assert outputs.map_path.exists()
    assert outputs.assumption_register_path.exists()
    assert outputs.manifest_path.exists()

    with outputs.ranked_csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["client_site_id"] == "SITE-CLIENT-01"
    assert rows[0]["opportunity_class"] == "A"
    assert rows[0]["recommendation"] == "prioritize"
    assert rows[0]["candidate_rte7000_id"] == ".ALPH"
    assert rows[0]["validation_depth"] == "geospatial_screening"

    with outputs.candidates_csv_path.open(newline="", encoding="utf-8") as handle:
        candidate_rows = list(csv.DictReader(handle))
    assert candidate_rows[0]["osm_id"] == "101"
    assert candidate_rows[0]["cartostock_id"] == "ALPHA7"
    assert candidate_rows[0]["distance_km"] == "1.33"

    report = outputs.report_path.read_text(encoding="utf-8")
    assert "# VoltPath - Portfolio Screening" in report
    assert "SITE-CLIENT-01" in report
    assert "pré-faisabilité côté acheteur" in report
    assert "ne remplace pas une étude officielle" in report

    map_html = outputs.map_path.read_text(encoding="utf-8")
    assert "<svg" in map_html
    assert "SITE-CLIENT-01" in map_html
    assert "Alpha" in map_html
    assert "<script src=" not in map_html

    assumptions = json.loads(
        outputs.assumption_register_path.read_text(encoding="utf-8")
    )
    assert assumptions["validation_depth"] == "geospatial_screening"
    assert assumptions["sources"]["openstreetmap"]["role"] == "geographic_context"
    assert assumptions["prohibited_claims"][0] == "guaranteed_connection_capacity"

    manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
    assert manifest["policy_version"] == result.policy_version
    assert manifest["created_at_utc"] == "2026-06-11T12:00:00+00:00"
    assert manifest["site_count"] == 1
    assert manifest["candidate_count"] == 1
    assert manifest["source_manifests"][0]["client_site_id"] == "SITE-CLIENT-01"
