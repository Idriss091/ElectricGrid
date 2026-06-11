from __future__ import annotations

from dataclasses import replace

from thesegrid.osm_substations import OsmSubstation
from thesegrid.portfolio_input import PortfolioSite
from thesegrid.public_data.evidence import PublicGridEvidenceProfile
from thesegrid.portfolio_screening import (
    PORTFOLIO_SCREENING_POLICY_VERSION,
    screen_portfolio,
)
from thesegrid.substation_identity import (
    CartostockSubstation,
    FrenchSubstationIdentity,
    OsmSubstationIdentityLink,
)


def _site(
    site_id: str,
    *,
    max_distance: float | None = None,
    land_status: str | None = "secured",
) -> PortfolioSite:
    return PortfolioSite(
        client_site_id=site_id,
        latitude=48.85,
        longitude=2.35,
        requested_mw=50.0,
        storage_duration_hours=2.0,
        land_control_status=land_status,
        target_connection_date="2028-09-30",
        max_connection_distance_km=max_distance,
        preferred_voltage_kv=225.0,
    )


def _cartostock() -> CartostockSubstation:
    return CartostockSubstation(
        cartostock_id="ALPHA7",
        address_label="POSTE 225kV N0 1 ALPHA",
        station_name="ALPHA",
        normalized_name="ALPHA",
        voltage_kv=225.0,
        commune_insee_code="75056",
        commune_name="Paris",
        nearby_demand="zone faisant l'objet de demandes",
        capacity_without_constraint="< 5 MW",
        turpe_zone="zone soutirage",
        injection_period="du 1er mai au 2 septembre inclus",
        gabarit="gabarit en injection",
        gabarit_substation_capacity="100 MW",
        gabarit_zone_name="Alpha",
        gabarit_zone_capacity="55 MW",
    )


def _identity(*, rte7000: bool = True) -> FrenchSubstationIdentity:
    return FrenchSubstationIdentity(
        cartostock_id="ALPHA7",
        cartostock_station_name="ALPHA",
        normalized_name="ALPHA",
        voltage_kv=225.0,
        commune_insee_code="75056",
        commune_name="Paris",
        odre_code=".ALPH",
        odre_name="ALPHA",
        rte7000_id=".ALPH" if rte7000 else None,
        match_confidence="exact",
        match_method="normalized_name_and_voltage",
        candidate_count=1,
        manual_review_required=False,
    )


def _link(
    *,
    distance_km: float = 3.0,
    identity: FrenchSubstationIdentity | None = None,
    confidence: str = "exact",
) -> OsmSubstationIdentityLink:
    substation = OsmSubstation(
        osm_type="way",
        osm_id=101,
        latitude=48.86,
        longitude=2.36,
        distance_km=distance_km,
        name="Alpha",
        normalized_name="ALPHA",
        reference=".ALPH",
        operator="RTE",
        operator_is_rte=True,
        voltage_levels_kv=(63.0, 225.0),
        source_url="https://www.openstreetmap.org/way/101",
    )
    return OsmSubstationIdentityLink(
        substation=substation,
        identity=_identity() if identity is None and confidence != "unmatched" else identity,
        match_confidence=confidence,  # type: ignore[arg-type]
        match_method="odre_code" if confidence != "unmatched" else "no_deterministic_match",
        candidate_count=1 if confidence != "unmatched" else 0,
        manual_review_required=confidence == "unmatched",
    )


def test_screen_portfolio_emits_six_explainable_dimensions_and_class_a_gate():
    site = _site("SITE-A")

    result = screen_portfolio(
        (site,),
        {"SITE-A": (_link(),)},
        (_cartostock(),),
    )

    screened = result.ranked_sites[0]
    assert result.policy_version == PORTFOLIO_SCREENING_POLICY_VERSION
    assert screened.total_score == 100
    assert [dimension.name for dimension in screened.dimensions] == [
        "connection_practicality",
        "evidence_quality",
        "grid_attractiveness",
        "flexible_connection_signal",
        "public_signal_completeness",
        "development_readiness",
    ]
    assert screened.opportunity_class == "A"
    assert screened.recommendation == "prioritize"
    assert screened.evidence_confidence == "high"
    assert screened.best_candidate is not None
    assert screened.best_candidate.identity is not None
    assert screened.next_action.startswith("Launch Deep Dive")


def test_screen_portfolio_uses_public_grid_evidence_for_score_and_deep_dive_trigger():
    site = _site("SITE-PUBLIC")
    public_evidence = PublicGridEvidenceProfile(
        client_site_id="SITE-PUBLIC",
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

    result = screen_portfolio(
        (site,),
        {"SITE-PUBLIC": (_link(),)},
        (_cartostock(),),
        public_evidence_profiles=(public_evidence,),
    )

    screened = result.ranked_sites[0]
    assert screened.best_candidate is not None
    assert screened.best_candidate.public_evidence == public_evidence
    assert [dimension.name for dimension in screened.dimensions][-1] == "public_grid_evidence"
    assert screened.dimensions[-1].points == 10
    assert screened.deep_dive_recommendation == "recommended"
    assert any(
        "ODRE/ECO2MIX public evidence is complete" in signal
        for signal in screened.strongest_positive_signals
    )


def test_screen_portfolio_requires_rte7000_link_for_class_a():
    site = _site("SITE-B")
    identity_without_rte7000 = _identity(rte7000=False)
    link = _link(identity=identity_without_rte7000)

    result = screen_portfolio(
        (site,),
        {"SITE-B": (link,)},
        (_cartostock(),),
    )

    screened = result.ranked_sites[0]
    assert screened.total_score >= 55
    assert screened.opportunity_class == "B"
    assert screened.recommendation == "investigate"
    assert screened.evidence_confidence == "medium"
    assert "RTE7000 topology link" in screened.missing_evidence


def test_screen_portfolio_rejects_candidate_outside_client_distance_limit():
    site = _site("SITE-C", max_distance=10.0)

    result = screen_portfolio(
        (site,),
        {"SITE-C": (_link(distance_km=20.0),)},
        (_cartostock(),),
    )

    screened = result.ranked_sites[0]
    assert screened.opportunity_class == "D"
    assert screened.recommendation == "reject"
    assert screened.best_candidate is not None
    assert screened.best_candidate.within_client_distance is False
    assert any("client distance limit" in item for item in screened.likely_constraints)


def test_screen_portfolio_distinguishes_no_candidate_from_source_unavailable():
    sites = (_site("NO-CANDIDATE"), _site("SOURCE-ERROR"))

    result = screen_portfolio(
        sites,
        {},
        (),
        source_errors={"SOURCE-ERROR": "Overpass timeout"},
    )
    by_id = {site.site.client_site_id: site for site in result.ranked_sites}

    assert by_id["NO-CANDIDATE"].opportunity_class == "D"
    assert "no transmission-level OSM candidate" in by_id["NO-CANDIDATE"].missing_evidence
    assert by_id["SOURCE-ERROR"].evidence_confidence == "unavailable"
    assert "OSM source unavailable: Overpass timeout" in by_id["SOURCE-ERROR"].missing_evidence


def test_screen_portfolio_ranking_is_deterministic_for_equal_scores():
    site_a = _site("A-SITE", land_status=None)
    site_b = replace(site_a, client_site_id="B-SITE")
    link_a = _link(distance_km=10.0)
    link_b = replace(
        link_a,
        substation=replace(link_a.substation, osm_id=102),
    )

    result = screen_portfolio(
        (site_b, site_a),
        {"A-SITE": (link_a,), "B-SITE": (link_b,)},
        (_cartostock(),),
    )

    assert [row.site.client_site_id for row in result.ranked_sites] == [
        "A-SITE",
        "B-SITE",
    ]
    assert [row.portfolio_rank for row in result.ranked_sites] == [1, 2]


def test_screen_portfolio_ranks_actionable_class_before_higher_raw_rejected_score():
    investigate_site = replace(
        _site("INVESTIGATE", land_status=None),
        requested_mw=200.0,
        target_connection_date=None,
    )
    rejected_site = _site("REJECTED", max_distance=10.0)

    result = screen_portfolio(
        (rejected_site, investigate_site),
        {
            "INVESTIGATE": (_link(distance_km=25.0),),
            "REJECTED": (_link(distance_km=20.0),),
        },
        (_cartostock(),),
    )

    assert result.ranked_sites[0].site.client_site_id == "INVESTIGATE"
    assert result.ranked_sites[0].opportunity_class == "B"
    assert result.ranked_sites[1].site.client_site_id == "REJECTED"
    assert result.ranked_sites[1].opportunity_class == "D"
    assert result.ranked_sites[1].total_score > result.ranked_sites[0].total_score


def test_screen_portfolio_prefers_candidate_inside_client_distance_limit():
    site = _site("SITE-LIMIT", max_distance=10.0)
    inside_unmatched = _link(
        distance_km=8.0,
        identity=None,
        confidence="unmatched",
    )
    outside_exact = replace(
        _link(distance_km=20.0),
        substation=replace(_link(distance_km=20.0).substation, osm_id=202),
    )

    result = screen_portfolio(
        (site,),
        {"SITE-LIMIT": (outside_exact, inside_unmatched)},
        (_cartostock(),),
    )

    screened = result.ranked_sites[0]
    assert screened.best_candidate is not None
    assert screened.best_candidate.substation.osm_id == 101
    assert screened.best_candidate.within_client_distance is True
    assert screened.opportunity_class == "C"
