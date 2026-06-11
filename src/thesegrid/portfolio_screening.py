from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Literal

from thesegrid.osm_substations import OsmSubstation
from thesegrid.portfolio_input import PortfolioSite
from thesegrid.substation_identity import (
    CartostockSubstation,
    FrenchSubstationIdentity,
    MatchConfidence,
    OsmSubstationIdentityLink,
    normalize_substation_name,
)


PORTFOLIO_SCREENING_POLICY_VERSION = "portfolio-geospatial-v0"

OpportunityClass = Literal["A", "B", "C", "D"]
Recommendation = Literal["prioritize", "investigate", "hold", "reject"]
EvidenceConfidence = Literal["high", "medium", "low", "unavailable"]


@dataclass(frozen=True)
class ScoreDimension:
    name: str
    points: int
    maximum_points: int
    reason: str


@dataclass(frozen=True)
class CandidateScreening:
    client_site_id: str
    substation: OsmSubstation
    identity: FrenchSubstationIdentity | None
    cartostock: CartostockSubstation | None
    match_confidence: MatchConfidence
    match_method: str
    within_client_distance: bool
    total_score: int
    dimensions: tuple[ScoreDimension, ...]


@dataclass(frozen=True)
class SiteScreening:
    portfolio_rank: int
    site: PortfolioSite
    total_score: int
    opportunity_class: OpportunityClass
    recommendation: Recommendation
    evidence_confidence: EvidenceConfidence
    best_candidate: CandidateScreening | None
    dimensions: tuple[ScoreDimension, ...]
    strongest_positive_signals: tuple[str, ...]
    likely_constraints: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class PortfolioScreeningResult:
    policy_version: str
    ranked_sites: tuple[SiteScreening, ...]
    candidate_assessments: tuple[CandidateScreening, ...]
    source_errors: Mapping[str, str]


def screen_portfolio(
    sites: Iterable[PortfolioSite],
    links_by_site: Mapping[str, Iterable[OsmSubstationIdentityLink]],
    cartostock_substations: Iterable[CartostockSubstation],
    *,
    source_errors: Mapping[str, str] | None = None,
) -> PortfolioScreeningResult:
    cartostock_by_id = {
        record.cartostock_id: record for record in cartostock_substations
    }
    errors = dict(source_errors or {})
    unsorted_sites: list[SiteScreening] = []
    all_candidates: list[CandidateScreening] = []

    for site in sites:
        candidates = tuple(
            _score_candidate(site, link, cartostock_by_id)
            for link in links_by_site.get(site.client_site_id, ())
        )
        all_candidates.extend(candidates)
        best_candidate = min(
            candidates,
            key=lambda candidate: (
                not candidate.within_client_distance,
                -candidate.total_score,
                candidate.substation.distance_km,
                candidate.substation.osm_type,
                candidate.substation.osm_id,
            ),
            default=None,
        )
        unsorted_sites.append(
            _build_site_screening(
                site,
                best_candidate,
                source_error=errors.get(site.client_site_id),
            )
        )

    ranked = tuple(
        replace(screening, portfolio_rank=rank)
        for rank, screening in enumerate(
            sorted(
                unsorted_sites,
                key=lambda screening: (
                    {"A": 0, "B": 1, "C": 2, "D": 3}[
                        screening.opportunity_class
                    ],
                    -screening.total_score,
                    screening.site.client_site_id,
                ),
            ),
            start=1,
        )
    )
    return PortfolioScreeningResult(
        policy_version=PORTFOLIO_SCREENING_POLICY_VERSION,
        ranked_sites=ranked,
        candidate_assessments=tuple(
            sorted(
                all_candidates,
                key=lambda candidate: (
                    candidate.client_site_id,
                    -candidate.total_score,
                    candidate.substation.distance_km,
                    candidate.substation.osm_id,
                ),
            )
        ),
        source_errors=errors,
    )


def _score_candidate(
    site: PortfolioSite,
    link: OsmSubstationIdentityLink,
    cartostock_by_id: Mapping[str, CartostockSubstation],
) -> CandidateScreening:
    identity = link.identity
    cartostock = (
        None if identity is None else cartostock_by_id.get(identity.cartostock_id)
    )
    within_distance = (
        site.max_connection_distance_km is None
        or link.substation.distance_km <= site.max_connection_distance_km
    )
    dimensions = (
        _practicality_dimension(site, link.substation, within_distance),
        _evidence_dimension(link),
        _grid_attractiveness_dimension(site, cartostock),
        _flexible_signal_dimension(site, cartostock),
        _public_completeness_dimension(cartostock),
        _readiness_dimension(site),
    )
    return CandidateScreening(
        client_site_id=site.client_site_id,
        substation=link.substation,
        identity=identity,
        cartostock=cartostock,
        match_confidence=link.match_confidence,
        match_method=link.match_method,
        within_client_distance=within_distance,
        total_score=sum(dimension.points for dimension in dimensions),
        dimensions=dimensions,
    )


def _build_site_screening(
    site: PortfolioSite,
    candidate: CandidateScreening | None,
    *,
    source_error: str | None,
) -> SiteScreening:
    dimensions = (
        _empty_dimensions(site)
        if candidate is None
        else candidate.dimensions
    )
    total_score = sum(dimension.points for dimension in dimensions)
    opportunity_class = _opportunity_class(candidate, total_score)
    recommendation: Recommendation = {
        "A": "prioritize",
        "B": "investigate",
        "C": "hold",
        "D": "reject",
    }[opportunity_class]
    evidence_confidence = _evidence_confidence(candidate, source_error)
    missing_evidence = _missing_evidence(candidate, source_error)
    constraints = _likely_constraints(site, candidate)
    positive_signals = tuple(
        dimension.reason
        for dimension in sorted(
            dimensions,
            key=lambda dimension: (-dimension.points, dimension.name),
        )
        if dimension.points > 0
    )
    return SiteScreening(
        portfolio_rank=0,
        site=site,
        total_score=total_score,
        opportunity_class=opportunity_class,
        recommendation=recommendation,
        evidence_confidence=evidence_confidence,
        best_candidate=candidate,
        dimensions=dimensions,
        strongest_positive_signals=positive_signals,
        likely_constraints=constraints,
        missing_evidence=missing_evidence,
        next_action=_next_action(opportunity_class),
    )


def _practicality_dimension(
    site: PortfolioSite,
    substation: OsmSubstation,
    within_distance: bool,
) -> ScoreDimension:
    if not within_distance:
        return ScoreDimension(
            "connection_practicality",
            0,
            30,
            (
                f"Nearest scored candidate is {substation.distance_km:.1f} km away, "
                f"beyond the client limit of {site.max_connection_distance_km:.1f} km."
            ),
        )
    distance = substation.distance_km
    if distance <= 5.0:
        points = 30
    elif distance <= 10.0:
        points = 25
    elif distance <= 20.0:
        points = 20
    elif distance <= 35.0:
        points = 12
    elif distance <= 50.0:
        points = 5
    else:
        points = 2
    return ScoreDimension(
        "connection_practicality",
        points,
        30,
        f"Straight-line distance to the candidate substation is {distance:.1f} km.",
    )


def _evidence_dimension(link: OsmSubstationIdentityLink) -> ScoreDimension:
    identity_points = {"exact": 15, "high": 10, "unmatched": 0}[
        link.match_confidence
    ]
    topology_points = (
        10
        if link.identity is not None and link.identity.rte7000_id is not None
        else 0
    )
    return ScoreDimension(
        "evidence_quality",
        identity_points + topology_points,
        25,
        (
            f"Substation match is {link.match_confidence} via {link.match_method}; "
            f"RTE7000 link is {'present' if topology_points else 'missing'}."
        ),
    )


def _grid_attractiveness_dimension(
    site: PortfolioSite,
    cartostock: CartostockSubstation | None,
) -> ScoreDimension:
    if cartostock is None:
        return ScoreDimension(
            "grid_attractiveness",
            0,
            15,
            "No linked Cartostock capacity signal.",
        )
    gabarit_capacity = _extract_mw(cartostock.gabarit_substation_capacity)
    if gabarit_capacity is not None:
        if gabarit_capacity >= site.requested_mw:
            points = 15
        elif gabarit_capacity >= site.requested_mw * 0.5:
            points = 10
        else:
            points = 5
        reason = (
            f"Cartostock substation gabarit signal is {gabarit_capacity:g} MW "
            f"for a {site.requested_mw:g} MW request."
        )
    elif cartostock.capacity_without_constraint:
        points = 2
        reason = (
            "Cartostock publishes only the weak capacity-without-constraint signal "
            f"'{cartostock.capacity_without_constraint}'."
        )
    else:
        points = 0
        reason = "Cartostock exposes no capacity-related signal for this identity."
    return ScoreDimension("grid_attractiveness", points, 15, reason)


def _flexible_signal_dimension(
    site: PortfolioSite,
    cartostock: CartostockSubstation | None,
) -> ScoreDimension:
    if cartostock is None:
        return ScoreDimension(
            "flexible_connection_signal",
            0,
            15,
            "No linked Cartostock gabarit signal.",
        )
    points = 8 if cartostock.gabarit else 0
    zone_capacity = _extract_mw(cartostock.gabarit_zone_capacity)
    if zone_capacity is not None:
        points += 7 if zone_capacity >= site.requested_mw else 3
    if points:
        reason = (
            f"Cartostock gabarit='{cartostock.gabarit or 'not specified'}', "
            f"zone capacity='{cartostock.gabarit_zone_capacity or 'not specified'}'."
        )
    else:
        reason = "No published Cartostock gabarit signal."
    return ScoreDimension("flexible_connection_signal", min(points, 15), 15, reason)


def _public_completeness_dimension(
    cartostock: CartostockSubstation | None,
) -> ScoreDimension:
    if cartostock is None:
        return ScoreDimension(
            "public_signal_completeness",
            0,
            5,
            "No linked Cartostock record.",
        )
    signals = (
        cartostock.capacity_without_constraint,
        cartostock.turpe_zone,
        cartostock.gabarit,
        cartostock.nearby_demand,
        cartostock.injection_period,
    )
    points = sum(value is not None for value in signals)
    return ScoreDimension(
        "public_signal_completeness",
        points,
        5,
        f"{points} of 5 selected Cartostock context fields are populated.",
    )


def _readiness_dimension(site: PortfolioSite) -> ScoreDimension:
    status = normalize_substation_name(site.land_control_status or "")
    if status in {
        "OWNED",
        "SECURED",
        "LEASESIGNED",
        "LANDSECURED",
        "MAITRISEFONCIERE",
    }:
        land_points = 7
    elif status in {"OPTION", "EXCLUSIVITY", "SOUSOPTION"}:
        land_points = 5
    elif status in {"NEGOTIATION", "UNDERNEGOTIATION", "PROSPECTING"}:
        land_points = 2
    else:
        land_points = 0
    date_points = 2 if site.target_connection_date else 0
    voltage_points = 1 if site.preferred_voltage_kv is not None else 0
    points = land_points + date_points + voltage_points
    return ScoreDimension(
        "development_readiness",
        points,
        10,
        (
            f"Land status contributes {land_points}/7; target date contributes "
            f"{date_points}/2; preferred voltage contributes {voltage_points}/1."
        ),
    )


def _empty_dimensions(site: PortfolioSite) -> tuple[ScoreDimension, ...]:
    return (
        ScoreDimension("connection_practicality", 0, 30, "No candidate substation."),
        ScoreDimension("evidence_quality", 0, 25, "No candidate substation."),
        ScoreDimension("grid_attractiveness", 0, 15, "No candidate substation."),
        ScoreDimension(
            "flexible_connection_signal",
            0,
            15,
            "No candidate substation.",
        ),
        ScoreDimension(
            "public_signal_completeness",
            0,
            5,
            "No candidate substation.",
        ),
        _readiness_dimension(site),
    )


def _opportunity_class(
    candidate: CandidateScreening | None,
    score: int,
) -> OpportunityClass:
    if candidate is None or not candidate.within_client_distance:
        return "D"
    has_class_a_evidence = (
        candidate.identity is not None
        and candidate.match_confidence in {"exact", "high"}
        and candidate.identity.rte7000_id is not None
    )
    if score >= 75 and has_class_a_evidence:
        return "A"
    if score >= 55:
        return "B"
    if score >= 30:
        return "C"
    return "D"


def _evidence_confidence(
    candidate: CandidateScreening | None,
    source_error: str | None,
) -> EvidenceConfidence:
    if source_error is not None:
        return "unavailable"
    if candidate is None or candidate.identity is None:
        return "low"
    if (
        candidate.match_confidence == "exact"
        and candidate.identity.rte7000_id is not None
    ):
        return "high"
    return "medium"


def _missing_evidence(
    candidate: CandidateScreening | None,
    source_error: str | None,
) -> tuple[str, ...]:
    if source_error is not None:
        return (f"OSM source unavailable: {source_error}",)
    if candidate is None:
        return ("no transmission-level OSM candidate",)
    missing: list[str] = []
    if candidate.identity is None:
        missing.append("canonical substation identity")
    elif candidate.identity.rte7000_id is None:
        missing.append("RTE7000 topology link")
    if candidate.cartostock is None:
        missing.append("Cartostock public signals")
    else:
        if candidate.cartostock.gabarit is None:
            missing.append("Cartostock flexible gabarit signal")
        if candidate.cartostock.gabarit_substation_capacity is None:
            missing.append("Cartostock substation gabarit capacity")
    return tuple(missing)


def _likely_constraints(
    site: PortfolioSite,
    candidate: CandidateScreening | None,
) -> tuple[str, ...]:
    constraints = ["Geographic proximity does not prove electrical connectability."]
    if candidate is None:
        constraints.append("No plausible transmission substation was observed in the search area.")
        return tuple(constraints)
    if not candidate.within_client_distance:
        constraints.append(
            (
                f"Candidate distance exceeds the client distance limit of "
                f"{site.max_connection_distance_km:g} km."
            )
        )
    if candidate.identity is None:
        constraints.append("Substation identity requires manual review.")
    if candidate.cartostock is not None and candidate.cartostock.gabarit is not None:
        constraints.append(
            "Cartostock gabarit is an indicative injection-oriented public signal."
        )
    if (
        site.preferred_voltage_kv is not None
        and candidate.substation.voltage_levels_kv
        and not any(
            abs(site.preferred_voltage_kv - voltage_kv) <= 0.5
            for voltage_kv in candidate.substation.voltage_levels_kv
        )
    ):
        constraints.append("Observed OSM voltages do not include the preferred voltage.")
    return tuple(constraints)


def _next_action(opportunity_class: OpportunityClass) -> str:
    return {
        "A": "Launch Deep Dive Site scoping and manually validate the canonical node.",
        "B": "Resolve missing identity or public evidence before Deep Dive selection.",
        "C": "Hold pending stronger grid or development-readiness evidence.",
        "D": "Reject from the current shortlist or revise the search-distance assumption.",
    }[opportunity_class]


def _extract_mw(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", value)
    if match is None:
        return None
    return float(match.group().replace(",", "."))
