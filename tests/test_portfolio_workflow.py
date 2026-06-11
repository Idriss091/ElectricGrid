from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from thesegrid.osm_substations import (
    OsmDataAccessError,
    OsmSourceManifest,
    OsmSubstation,
    OsmSubstationResult,
)
from thesegrid.portfolio_workflow import (
    PortfolioWorkflowRequest,
    run_portfolio_workflow,
)
from thesegrid.rte7000_data import (
    Rte7000PartitionManifest,
    Rte7000PartitionResult,
)
from thesegrid.substation_identity import (
    OdreSourceManifest,
    OdreSubstation,
    OdreSubstationResult,
)


def _write_portfolio(path):
    path.write_text(
        "client_site_id,latitude,longitude,requested_mw,storage_duration_hours,"
        "land_control_status,target_connection_date,preferred_voltage_kv\n"
        "SITE-01,48.85,2.35,50,2,secured,2028-09-30,225\n",
        encoding="utf-8",
    )


def _write_cartostock(path):
    path.write_text(
        "IDRPoste;ADRPoste;CodeCommuneINSEE;NomCommune;DemandeProximite;"
        "CapaciteSansContrainte;ZoneTarifaireTURPE;PlageTarifInjection;Gabarit;"
        "CapacitePosteGabarit;NomZoneGabarit;CapaciteZoneGabarit\n"
        "ALPHA7;POSTE 225kV N0 1 ALPHA;75056;Paris;;< 5 MW;zone soutirage;;"
        "gabarit en injection;100 MW;Alpha;55 MW\n",
        encoding="utf-8",
    )


def _odre_result():
    return OdreSubstationResult(
        substations=(
            OdreSubstation(
                odre_code=".ALPH",
                name="ALPHA",
                normalized_name="ALPHA",
                voltage_kv=225.0,
                function="Poste",
                status="EN EXPLOITATION",
                department="Paris",
            ),
        ),
        manifest=OdreSourceManifest(
            source_url="https://odre.test/substations.csv",
            source_type="public_signal",
            row_count=1,
            retrieved_at_utc="2026-06-11T10:00:00+00:00",
        ),
    )


def _rte_result(request):
    return Rte7000PartitionResult(
        frame=pd.DataFrame({"id": [".ALPH"], "name": ["ALPHA"]}),
        manifest=Rte7000PartitionManifest(
            repository=request.repository,
            revision=request.revision,
            remote_path=request.remote_path,
            component=request.component,
            year=request.year,
            month=request.month,
            columns=request.columns,
            filters=request.filters,
            source_type="public_reconstruction",
            row_count=1,
            retrieved_at_utc="2026-06-11T10:00:00+00:00",
        ),
    )


def _osm_result(site, *, radius_km):
    return OsmSubstationResult(
        substations=(
            OsmSubstation(
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
                voltage_levels_kv=(225.0,),
                source_url="https://www.openstreetmap.org/way/101",
            ),
        ),
        manifest=OsmSourceManifest(
            endpoint="fixture://overpass",
            query="[out:json];...",
            client_site_id=site.client_site_id,
            radius_km=radius_km,
            returned_element_count=1,
            returned_candidate_count=1,
            retrieved_at_utc="2026-06-11T10:00:00+00:00",
            attribution="© OpenStreetMap contributors, ODbL 1.0",
        ),
    )


def test_run_portfolio_workflow_uses_projected_pinned_rte_snapshot_and_writes_bundle(
    tmp_path,
):
    portfolio_path = tmp_path / "portfolio.csv"
    cartostock_path = tmp_path / "cartostock.csv"
    output_dir = tmp_path / "output"
    _write_portfolio(portfolio_path)
    _write_cartostock(cartostock_path)
    captured = {}

    def rte_reader(request):
        captured["request"] = request
        return _rte_result(request)

    result = run_portfolio_workflow(
        PortfolioWorkflowRequest(
            portfolio_path=portfolio_path,
            cartostock_path=cartostock_path,
            output_dir=output_dir,
            rte7000_revision="1a2419a6f8a81ab212af035e811d4b893d7c4ccf",
            rte7000_year=2023,
            rte7000_month=1,
            rte7000_snapshot="2023-01-01T00:00:00",
            search_radius_km=35.0,
        ),
        odre_loader=_odre_result,
        rte_reader=rte_reader,
        osm_discoverer=_osm_result,
        now=lambda: datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
    )

    request = captured["request"]
    assert request.component == "sub"
    assert request.columns == ("id", "name")
    assert request.filters == (("datetime", datetime(2023, 1, 1, 0, 0)),)
    assert request.remote_path.endswith("/sub/sub_2023-01.parquet")
    assert result.screening.ranked_sites[0].opportunity_class == "A"
    assert result.outputs.report_path.exists()
    assert result.outputs.manifest_path.exists()


def test_run_portfolio_workflow_keeps_site_visible_when_osm_source_fails(tmp_path):
    portfolio_path = tmp_path / "portfolio.csv"
    cartostock_path = tmp_path / "cartostock.csv"
    _write_portfolio(portfolio_path)
    _write_cartostock(cartostock_path)

    def failed_osm(_site, *, radius_km):
        raise OsmDataAccessError(f"timeout at {radius_km:g} km")

    result = run_portfolio_workflow(
        PortfolioWorkflowRequest(
            portfolio_path=portfolio_path,
            cartostock_path=cartostock_path,
            output_dir=tmp_path / "output",
            rte7000_revision="1a2419a6f8a81ab212af035e811d4b893d7c4ccf",
        ),
        odre_loader=_odre_result,
        rte_reader=_rte_result,
        osm_discoverer=failed_osm,
    )

    screened = result.screening.ranked_sites[0]
    assert screened.opportunity_class == "D"
    assert screened.evidence_confidence == "unavailable"
    assert "SITE-01" in result.screening.source_errors


def test_run_portfolio_workflow_can_use_per_site_osm_fixture(tmp_path):
    portfolio_path = tmp_path / "portfolio.csv"
    cartostock_path = tmp_path / "cartostock.csv"
    fixture_path = tmp_path / "osm_fixture.json"
    _write_portfolio(portfolio_path)
    _write_cartostock(cartostock_path)
    fixture_path.write_text(
        json.dumps(
            {
                "SITE-01": {
                    "elements": [
                        {
                            "type": "way",
                            "id": 101,
                            "center": {"lat": 48.86, "lon": 2.36},
                            "tags": {
                                "power": "substation",
                                "name": "Alpha",
                                "ref": ".ALPH",
                                "operator": "RTE",
                                "voltage": "225000",
                            },
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_portfolio_workflow(
        PortfolioWorkflowRequest(
            portfolio_path=portfolio_path,
            cartostock_path=cartostock_path,
            output_dir=tmp_path / "output",
            rte7000_revision="1a2419a6f8a81ab212af035e811d4b893d7c4ccf",
            osm_fixture_path=fixture_path,
        ),
        odre_loader=_odre_result,
        rte_reader=_rte_result,
    )

    assert result.screening.ranked_sites[0].opportunity_class == "A"
    manifest = json.loads(result.outputs.manifest_path.read_text(encoding="utf-8"))
    fixture_sources = [
        source
        for source in manifest["source_manifests"]
        if source.get("source_type") == "osm_overpass_fixture"
    ]
    assert len(fixture_sources) == 1


def test_portfolio_workflow_is_available_from_public_api():
    from thesegrid import PortfolioWorkflowRequest as PublicRequest
    from thesegrid import run_portfolio_workflow as public_run

    assert PublicRequest is PortfolioWorkflowRequest
    assert public_run is run_portfolio_workflow
