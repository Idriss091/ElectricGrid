from __future__ import annotations

import csv
import json
from datetime import UTC, datetime

from thesegrid.osm_substations import OsmSourceManifest, OsmSubstation
from thesegrid.portfolio_input import PortfolioSite
from thesegrid.portfolio_reporting import write_portfolio_screening_outputs
from thesegrid.portfolio_screening import screen_portfolio
from thesegrid.public_data.evidence import PublicGridEvidenceProfile
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
    public_evidence = PublicGridEvidenceProfile(
        client_site_id="SITE-CLIENT-01",
        region="BRETAGNE",
        odre_code=".ALPH",
        regional_constraint_count=2,
        dominant_constraint_occurrence="Forte : entre 75 et 150 fois par an",
        dominant_constraint_duration="]2h-4h]",
        high_persistence_constraint_count=1,
        battery_storage_kw_region=1500.0,
        battery_storage_kwh_region=3000.0,
        battery_storage_kw_source_substation=1200.0,
        latest_regional_load_date="2026-06-09",
        eco2mix_coverage_hours=35136,
        source_completeness_score=1.0,
        missing_evidence=(),
    )
    return screen_portfolio(
        (site,),
        {"SITE-CLIENT-01": (link,)},
        (cartostock,),
        public_evidence_profiles=(public_evidence,),
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
    assert outputs.public_grid_evidence_csv_path.exists()
    assert outputs.deep_dive_shortlist_csv_path.exists()
    assert outputs.deep_dive_inputs_dir_path.is_dir()
    assert outputs.site_finder_seed_signals_csv_path.exists()
    assert outputs.bundle_summary_path.exists()
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
    assert rows[0]["public_grid_evidence_score"] == "10"
    assert rows[0]["deep_dive_recommendation"] == "recommended"
    assert rows[0]["validation_depth"] == "geospatial_screening"

    with outputs.public_grid_evidence_csv_path.open(newline="", encoding="utf-8") as handle:
        evidence_rows = list(csv.DictReader(handle))
    assert evidence_rows[0]["client_site_id"] == "SITE-CLIENT-01"
    assert evidence_rows[0]["region"] == "BRETAGNE"
    assert evidence_rows[0]["battery_storage_kw_region"] == "1500.0"

    with outputs.deep_dive_shortlist_csv_path.open(
        newline="", encoding="utf-8"
    ) as handle:
        shortlist_rows = list(csv.DictReader(handle))
    assert len(shortlist_rows) == 1
    assert shortlist_rows[0]["client_site_id"] == "SITE-CLIENT-01"
    assert shortlist_rows[0]["deep_dive_recommendation"] == "recommended"
    assert shortlist_rows[0]["candidate_rte7000_id"] == ".ALPH"
    assert shortlist_rows[0]["public_grid_evidence_score"] == "10"
    assert shortlist_rows[0]["source_completeness_score"] == "1.0"

    deep_dive_package_path = (
        outputs.deep_dive_inputs_dir_path / "SITE-CLIENT-01.json"
    )
    assert deep_dive_package_path.exists()
    deep_dive_package = json.loads(deep_dive_package_path.read_text(encoding="utf-8"))
    assert deep_dive_package["package_type"] == "deep_dive_site_input"
    assert deep_dive_package["client_site_id"] == "SITE-CLIENT-01"
    assert deep_dive_package["screening"]["deep_dive_recommendation"] == "recommended"
    assert deep_dive_package["site"]["requested_mw"] == 50.0
    assert deep_dive_package["candidate"]["rte7000_id"] == ".ALPH"
    assert deep_dive_package["candidate"]["odre_code"] == ".ALPH"
    assert deep_dive_package["public_grid_evidence"]["region"] == "BRETAGNE"
    assert "Map RTE7000 id to the power-flow bus before simulation." in (
        deep_dive_package["manual_validation_checklist"]
    )
    assert "official_connection_feasibility" in deep_dive_package["prohibited_claims"]

    with outputs.site_finder_seed_signals_csv_path.open(
        newline="", encoding="utf-8"
    ) as handle:
        seed_rows = list(csv.DictReader(handle))
    assert len(seed_rows) == 1
    assert seed_rows[0]["source_client_site_id"] == "SITE-CLIENT-01"
    assert seed_rows[0]["candidate_name"] == "Alpha"
    assert seed_rows[0]["odre_code"] == ".ALPH"
    assert seed_rows[0]["rte7000_id"] == ".ALPH"
    assert seed_rows[0]["region"] == "BRETAGNE"
    assert seed_rows[0]["seed_use"] == "site_finder_reference_substation"

    bundle_summary = json.loads(outputs.bundle_summary_path.read_text(encoding="utf-8"))
    assert bundle_summary["package_type"] == "portfolio_screening_bundle_summary"
    assert bundle_summary["site_count"] == 1
    assert bundle_summary["candidate_count"] == 1
    assert bundle_summary["site_finder_seed_count"] == 1
    assert bundle_summary["opportunity_class_counts"] == {
        "A": 1,
        "B": 0,
        "C": 0,
        "D": 0,
    }
    assert bundle_summary["deep_dive_recommendation_counts"]["recommended"] == 1
    assert bundle_summary["deep_dive_shortlist_count"] == 1
    assert bundle_summary["top_ranked_site"]["client_site_id"] == "SITE-CLIENT-01"

    with outputs.candidates_csv_path.open(newline="", encoding="utf-8") as handle:
        candidate_rows = list(csv.DictReader(handle))
    assert candidate_rows[0]["osm_id"] == "101"
    assert candidate_rows[0]["cartostock_id"] == "ALPHA7"
    assert candidate_rows[0]["distance_km"] == "1.33"

    report = outputs.report_path.read_text(encoding="utf-8")
    assert "# VoltPath - Portfolio Screening" in report
    assert "SITE-CLIENT-01" in report
    assert "Recommended Deep Dive Shortlist" in report
    assert "ODRE and ECO2MIX are public-context evidence" in report
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
    assert manifest["outputs"]["deep_dive_shortlist"] == "deep_dive_shortlist.csv"
    assert manifest["outputs"]["deep_dive_inputs"] == "deep_dive_inputs"
    assert (
        manifest["outputs"]["site_finder_seed_signals"]
        == "site_finder_seed_signals.csv"
    )
    assert manifest["outputs"]["bundle_summary"] == "portfolio_bundle_summary.json"
