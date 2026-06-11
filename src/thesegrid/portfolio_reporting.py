from __future__ import annotations

import csv
import html
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from thesegrid.portfolio_screening import (
    CandidateScreening,
    PortfolioScreeningResult,
    SiteScreening,
)


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class PortfolioScreeningOutputs:
    ranked_csv_path: Path
    candidates_csv_path: Path
    public_grid_evidence_csv_path: Path
    deep_dive_shortlist_csv_path: Path
    deep_dive_inputs_dir_path: Path
    site_finder_seed_signals_csv_path: Path
    bundle_summary_path: Path
    report_path: Path
    map_path: Path
    assumption_register_path: Path
    manual_review_queue_path: Path
    data_quality_report_path: Path
    manifest_path: Path


def write_portfolio_screening_outputs(
    result: PortfolioScreeningResult,
    output_dir: Path,
    *,
    source_manifests: Iterable[object] = (),
    now: Clock | None = None,
) -> PortfolioScreeningOutputs:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_manifest_values = tuple(_json_value(item) for item in source_manifests)
    outputs = PortfolioScreeningOutputs(
        ranked_csv_path=output_dir / "portfolio_ranked.csv",
        candidates_csv_path=output_dir / "candidate_substations.csv",
        public_grid_evidence_csv_path=output_dir / "public_grid_evidence.csv",
        deep_dive_shortlist_csv_path=output_dir / "deep_dive_shortlist.csv",
        deep_dive_inputs_dir_path=output_dir / "deep_dive_inputs",
        site_finder_seed_signals_csv_path=output_dir / "site_finder_seed_signals.csv",
        bundle_summary_path=output_dir / "portfolio_bundle_summary.json",
        report_path=output_dir / "portfolio_screening_report.md",
        map_path=output_dir / "portfolio_screening_map.html",
        assumption_register_path=output_dir / "source_assumption_register.json",
        manual_review_queue_path=output_dir / "manual_review_queue.csv",
        data_quality_report_path=output_dir / "data_quality_report.json",
        manifest_path=output_dir / "run_manifest.json",
    )
    _write_ranked_csv(result, outputs.ranked_csv_path)
    _write_candidates_csv(result, outputs.candidates_csv_path)
    _write_public_grid_evidence_csv(result, outputs.public_grid_evidence_csv_path)
    _write_deep_dive_shortlist_csv(result, outputs.deep_dive_shortlist_csv_path)
    _write_deep_dive_input_packages(result, outputs.deep_dive_inputs_dir_path)
    _write_site_finder_seed_signals_csv(
        result,
        outputs.site_finder_seed_signals_csv_path,
    )
    _write_manual_review_queue_csv(result, outputs.manual_review_queue_path)
    outputs.bundle_summary_path.write_text(
        json.dumps(_bundle_summary(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    outputs.report_path.write_text(_render_report(result), encoding="utf-8")
    outputs.map_path.write_text(_render_map(result), encoding="utf-8")
    outputs.assumption_register_path.write_text(
        json.dumps(_assumption_register(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    outputs.data_quality_report_path.write_text(
        json.dumps(
            _data_quality_report(result, source_manifest_values),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    created_at = (now or _utc_now)()
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    created_at = created_at.astimezone(UTC)
    manifest = {
        "product": "VoltPath Portfolio Screening",
        "policy_version": result.policy_version,
        "validation_depth": "geospatial_screening",
        "created_at_utc": created_at.isoformat(),
        "site_count": len(result.ranked_sites),
        "candidate_count": len(result.candidate_assessments),
        "source_errors": dict(result.source_errors),
        "source_manifests": list(source_manifest_values),
        "outputs": {
            "ranked_portfolio": outputs.ranked_csv_path.name,
            "candidate_substations": outputs.candidates_csv_path.name,
            "public_grid_evidence": outputs.public_grid_evidence_csv_path.name,
            "deep_dive_shortlist": outputs.deep_dive_shortlist_csv_path.name,
            "deep_dive_inputs": outputs.deep_dive_inputs_dir_path.name,
            "site_finder_seed_signals": (
                outputs.site_finder_seed_signals_csv_path.name
            ),
            "bundle_summary": outputs.bundle_summary_path.name,
            "report": outputs.report_path.name,
            "map": outputs.map_path.name,
            "assumption_register": outputs.assumption_register_path.name,
            "manual_review_queue": outputs.manual_review_queue_path.name,
            "data_quality_report": outputs.data_quality_report_path.name,
        },
    }
    outputs.manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return outputs


def _write_ranked_csv(result: PortfolioScreeningResult, path: Path) -> None:
    fieldnames = (
        "portfolio_rank",
        "client_site_id",
        "latitude",
        "longitude",
        "requested_mw",
        "storage_duration_hours",
        "total_score",
        "opportunity_class",
        "recommendation",
        "evidence_confidence",
        "candidate_name",
        "candidate_distance_km",
        "candidate_voltage_kv",
        "candidate_cartostock_id",
        "candidate_odre_code",
        "candidate_rte7000_id",
        "match_confidence",
        "connection_practicality_score",
        "evidence_quality_score",
        "grid_attractiveness_score",
        "flexible_connection_signal_score",
        "public_signal_completeness_score",
        "development_readiness_score",
        "public_grid_evidence_score",
        "deep_dive_recommendation",
        "manual_review_required",
        "manual_review_status",
        "manual_review_reviewer",
        "manual_reviewed_at_utc",
        "manual_review_notes",
        "strongest_positive_signals",
        "likely_constraints",
        "missing_evidence",
        "next_action",
        "validation_depth",
        "policy_version",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for screening in result.ranked_sites:
            writer.writerow(_ranked_row(screening, result.policy_version))


def _ranked_row(screening: SiteScreening, policy_version: str) -> dict[str, object]:
    candidate = screening.best_candidate
    identity = None if candidate is None else candidate.identity
    dimensions = {dimension.name: dimension.points for dimension in screening.dimensions}
    voltage = _candidate_voltage(candidate)
    return {
        "portfolio_rank": screening.portfolio_rank,
        "client_site_id": screening.site.client_site_id,
        "latitude": screening.site.latitude,
        "longitude": screening.site.longitude,
        "requested_mw": screening.site.requested_mw,
        "storage_duration_hours": screening.site.storage_duration_hours,
        "total_score": screening.total_score,
        "opportunity_class": screening.opportunity_class,
        "recommendation": screening.recommendation,
        "evidence_confidence": screening.evidence_confidence,
        "candidate_name": (
            "" if candidate is None else candidate.substation.name or ""
        ),
        "candidate_distance_km": (
            "" if candidate is None else f"{candidate.substation.distance_km:.2f}"
        ),
        "candidate_voltage_kv": "" if voltage is None else f"{voltage:g}",
        "candidate_cartostock_id": "" if identity is None else identity.cartostock_id,
        "candidate_odre_code": (
            "" if identity is None or identity.odre_code is None else identity.odre_code
        ),
        "candidate_rte7000_id": (
            ""
            if identity is None or identity.rte7000_id is None
            else identity.rte7000_id
        ),
        "match_confidence": (
            "" if candidate is None else candidate.match_confidence
        ),
        "connection_practicality_score": dimensions["connection_practicality"],
        "evidence_quality_score": dimensions["evidence_quality"],
        "grid_attractiveness_score": dimensions["grid_attractiveness"],
        "flexible_connection_signal_score": dimensions[
            "flexible_connection_signal"
        ],
        "public_signal_completeness_score": dimensions[
            "public_signal_completeness"
        ],
        "development_readiness_score": dimensions["development_readiness"],
        "public_grid_evidence_score": dimensions.get("public_grid_evidence", 0),
        "deep_dive_recommendation": screening.deep_dive_recommendation,
        "manual_review_required": screening.manual_review_required,
        "manual_review_status": screening.manual_review_status,
        "manual_review_reviewer": screening.manual_review_reviewer,
        "manual_reviewed_at_utc": screening.manual_reviewed_at_utc,
        "manual_review_notes": screening.manual_review_notes,
        "strongest_positive_signals": " | ".join(
            screening.strongest_positive_signals
        ),
        "likely_constraints": " | ".join(screening.likely_constraints),
        "missing_evidence": " | ".join(screening.missing_evidence),
        "next_action": screening.next_action,
        "validation_depth": "geospatial_screening",
        "policy_version": policy_version,
    }


def _write_candidates_csv(result: PortfolioScreeningResult, path: Path) -> None:
    fieldnames = (
        "client_site_id",
        "osm_type",
        "osm_id",
        "osm_name",
        "osm_reference",
        "operator",
        "latitude",
        "longitude",
        "distance_km",
        "voltage_levels_kv",
        "within_client_distance",
        "match_confidence",
        "match_method",
        "cartostock_id",
        "odre_code",
        "rte7000_id",
        "candidate_score",
        "source_url",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in result.candidate_assessments:
            identity = candidate.identity
            writer.writerow(
                {
                    "client_site_id": candidate.client_site_id,
                    "osm_type": candidate.substation.osm_type,
                    "osm_id": candidate.substation.osm_id,
                    "osm_name": candidate.substation.name or "",
                    "osm_reference": candidate.substation.reference or "",
                    "operator": candidate.substation.operator or "",
                    "latitude": candidate.substation.latitude,
                    "longitude": candidate.substation.longitude,
                    "distance_km": f"{candidate.substation.distance_km:.2f}",
                    "voltage_levels_kv": "|".join(
                        f"{level:g}"
                        for level in candidate.substation.voltage_levels_kv
                    ),
                    "within_client_distance": candidate.within_client_distance,
                    "match_confidence": candidate.match_confidence,
                    "match_method": candidate.match_method,
                    "cartostock_id": (
                        "" if identity is None else identity.cartostock_id
                    ),
                    "odre_code": (
                        ""
                        if identity is None or identity.odre_code is None
                        else identity.odre_code
                    ),
                    "rte7000_id": (
                        ""
                        if identity is None or identity.rte7000_id is None
                        else identity.rte7000_id
                    ),
                    "candidate_score": candidate.total_score,
                    "source_url": candidate.substation.source_url,
                }
            )


def _write_public_grid_evidence_csv(result: PortfolioScreeningResult, path: Path) -> None:
    fieldnames = (
        "client_site_id",
        "region",
        "odre_code",
        "regional_constraint_count",
        "dominant_constraint_occurrence",
        "dominant_constraint_duration",
        "high_persistence_constraint_count",
        "battery_storage_kw_region",
        "battery_storage_kwh_region",
        "battery_storage_kw_source_substation",
        "latest_regional_load_date",
        "eco2mix_record_count",
        "eco2mix_source_interval_minutes",
        "eco2mix_observed_consumption_count",
        "eco2mix_missing_consumption_count",
        "eco2mix_coverage_hours",
        "source_completeness_score",
        "missing_evidence",
    )
    seen: set[tuple[str, str]] = set()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in result.candidate_assessments:
            profile = candidate.public_evidence
            if profile is None:
                continue
            key = (profile.client_site_id, profile.odre_code)
            if key in seen:
                continue
            seen.add(key)
            writer.writerow(
                {
                    "client_site_id": profile.client_site_id,
                    "region": profile.region,
                    "odre_code": profile.odre_code,
                    "regional_constraint_count": profile.regional_constraint_count,
                    "dominant_constraint_occurrence": profile.dominant_constraint_occurrence,
                    "dominant_constraint_duration": profile.dominant_constraint_duration,
                    "high_persistence_constraint_count": (
                        profile.high_persistence_constraint_count
                    ),
                    "battery_storage_kw_region": profile.battery_storage_kw_region,
                    "battery_storage_kwh_region": profile.battery_storage_kwh_region,
                    "battery_storage_kw_source_substation": (
                        profile.battery_storage_kw_source_substation
                    ),
                    "latest_regional_load_date": profile.latest_regional_load_date,
                    "eco2mix_record_count": profile.eco2mix_record_count,
                    "eco2mix_source_interval_minutes": (
                        ""
                        if profile.eco2mix_source_interval_minutes is None
                        else profile.eco2mix_source_interval_minutes
                    ),
                    "eco2mix_observed_consumption_count": (
                        profile.eco2mix_observed_consumption_count
                    ),
                    "eco2mix_missing_consumption_count": (
                        profile.eco2mix_missing_consumption_count
                    ),
                    "eco2mix_coverage_hours": profile.eco2mix_coverage_hours,
                    "source_completeness_score": profile.source_completeness_score,
                    "missing_evidence": " | ".join(profile.missing_evidence),
                }
            )


def _write_deep_dive_shortlist_csv(
    result: PortfolioScreeningResult, path: Path
) -> None:
    fieldnames = (
        "portfolio_rank",
        "client_site_id",
        "deep_dive_recommendation",
        "opportunity_class",
        "total_score",
        "requested_mw",
        "storage_duration_hours",
        "candidate_name",
        "candidate_distance_km",
        "candidate_voltage_kv",
        "candidate_cartostock_id",
        "candidate_odre_code",
        "candidate_rte7000_id",
        "match_confidence",
        "public_grid_evidence_score",
        "source_completeness_score",
        "regional_constraint_count",
        "latest_regional_load_date",
        "next_action",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for screening in result.ranked_sites:
            if screening.deep_dive_recommendation not in {
                "recommended",
                "conditional",
            }:
                continue
            writer.writerow(_deep_dive_shortlist_row(screening))


def _write_manual_review_queue_csv(
    result: PortfolioScreeningResult,
    path: Path,
) -> None:
    fieldnames = (
        "portfolio_rank",
        "client_site_id",
        "opportunity_class",
        "manual_review_required",
        "manual_review_status",
        "manual_review_reviewer",
        "manual_reviewed_at_utc",
        "manual_review_notes",
        "candidate_name",
        "candidate_cartostock_id",
        "candidate_odre_code",
        "candidate_rte7000_id",
        "match_confidence",
        "next_action",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for screening in result.ranked_sites:
            if not screening.manual_review_required:
                continue
            candidate = screening.best_candidate
            identity = None if candidate is None else candidate.identity
            writer.writerow(
                {
                    "portfolio_rank": screening.portfolio_rank,
                    "client_site_id": screening.site.client_site_id,
                    "opportunity_class": screening.opportunity_class,
                    "manual_review_required": screening.manual_review_required,
                    "manual_review_status": screening.manual_review_status,
                    "manual_review_reviewer": screening.manual_review_reviewer,
                    "manual_reviewed_at_utc": screening.manual_reviewed_at_utc,
                    "manual_review_notes": screening.manual_review_notes,
                    "candidate_name": (
                        "" if candidate is None else candidate.substation.name or ""
                    ),
                    "candidate_cartostock_id": (
                        "" if identity is None else identity.cartostock_id
                    ),
                    "candidate_odre_code": (
                        ""
                        if identity is None or identity.odre_code is None
                        else identity.odre_code
                    ),
                    "candidate_rte7000_id": (
                        ""
                        if identity is None or identity.rte7000_id is None
                        else identity.rte7000_id
                    ),
                    "match_confidence": (
                        "" if candidate is None else candidate.match_confidence
                    ),
                    "next_action": screening.next_action,
                }
            )


def _deep_dive_shortlist_row(screening: SiteScreening) -> dict[str, object]:
    candidate = screening.best_candidate
    identity = None if candidate is None else candidate.identity
    profile = None if candidate is None else candidate.public_evidence
    dimensions = {dimension.name: dimension.points for dimension in screening.dimensions}
    voltage = _candidate_voltage(candidate)
    return {
        "portfolio_rank": screening.portfolio_rank,
        "client_site_id": screening.site.client_site_id,
        "deep_dive_recommendation": screening.deep_dive_recommendation,
        "opportunity_class": screening.opportunity_class,
        "total_score": screening.total_score,
        "requested_mw": screening.site.requested_mw,
        "storage_duration_hours": screening.site.storage_duration_hours,
        "candidate_name": "" if candidate is None else candidate.substation.name or "",
        "candidate_distance_km": (
            "" if candidate is None else f"{candidate.substation.distance_km:.2f}"
        ),
        "candidate_voltage_kv": "" if voltage is None else f"{voltage:g}",
        "candidate_cartostock_id": "" if identity is None else identity.cartostock_id,
        "candidate_odre_code": (
            "" if identity is None or identity.odre_code is None else identity.odre_code
        ),
        "candidate_rte7000_id": (
            ""
            if identity is None or identity.rte7000_id is None
            else identity.rte7000_id
        ),
        "match_confidence": "" if candidate is None else candidate.match_confidence,
        "public_grid_evidence_score": dimensions.get("public_grid_evidence", 0),
        "source_completeness_score": (
            "" if profile is None else profile.source_completeness_score
        ),
        "regional_constraint_count": (
            "" if profile is None else profile.regional_constraint_count
        ),
        "latest_regional_load_date": (
            "" if profile is None else profile.latest_regional_load_date
        ),
        "next_action": screening.next_action,
    }


def _write_deep_dive_input_packages(
    result: PortfolioScreeningResult, directory: Path
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for screening in result.ranked_sites:
        if screening.deep_dive_recommendation not in {
            "recommended",
            "conditional",
        }:
            continue
        path = directory / f"{_safe_filename(screening.site.client_site_id)}.json"
        path.write_text(
            json.dumps(
                _deep_dive_input_package(screening, result.policy_version),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )


def _write_site_finder_seed_signals_csv(
    result: PortfolioScreeningResult, path: Path
) -> None:
    fieldnames = (
        "seed_rank",
        "source_client_site_id",
        "candidate_name",
        "region",
        "odre_code",
        "rte7000_id",
        "cartostock_id",
        "voltage_kv",
        "source_site_distance_km",
        "opportunity_class",
        "deep_dive_recommendation",
        "total_score",
        "public_grid_evidence_score",
        "source_completeness_score",
        "regional_constraint_count",
        "battery_storage_kw_region",
        "battery_storage_kw_source_substation",
        "latest_regional_load_date",
        "seed_use",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rank, screening in enumerate(_site_finder_seed_screenings(result), start=1):
            writer.writerow(_site_finder_seed_row(rank, screening))


def _site_finder_seed_screenings(
    result: PortfolioScreeningResult,
) -> tuple[SiteScreening, ...]:
    by_key: dict[str, SiteScreening] = {}
    for screening in result.ranked_sites:
        if screening.deep_dive_recommendation not in {
            "recommended",
            "conditional",
        }:
            continue
        candidate = screening.best_candidate
        if candidate is None:
            continue
        key = _site_finder_seed_key(candidate)
        previous = by_key.get(key)
        if previous is None or _seed_sort_key(screening) < _seed_sort_key(previous):
            by_key[key] = screening
    return tuple(sorted(by_key.values(), key=_seed_sort_key))


def _site_finder_seed_key(candidate: CandidateScreening) -> str:
    identity = candidate.identity
    if identity is not None:
        if identity.rte7000_id:
            return f"rte7000:{identity.rte7000_id}"
        if identity.odre_code:
            return f"odre:{identity.odre_code}"
        return f"cartostock:{identity.cartostock_id}"
    return f"osm:{candidate.substation.osm_type}:{candidate.substation.osm_id}"


def _seed_sort_key(screening: SiteScreening) -> tuple[int, int, int, str]:
    recommendation_rank = {
        "recommended": 0,
        "conditional": 1,
        "not_recommended": 2,
    }[screening.deep_dive_recommendation]
    class_rank = {"A": 0, "B": 1, "C": 2, "D": 3}[screening.opportunity_class]
    return (
        recommendation_rank,
        class_rank,
        -screening.total_score,
        screening.site.client_site_id,
    )


def _site_finder_seed_row(rank: int, screening: SiteScreening) -> dict[str, object]:
    candidate = screening.best_candidate
    assert candidate is not None
    identity = candidate.identity
    profile = candidate.public_evidence
    dimensions = {dimension.name: dimension.points for dimension in screening.dimensions}
    voltage = _candidate_voltage(candidate)
    return {
        "seed_rank": rank,
        "source_client_site_id": screening.site.client_site_id,
        "candidate_name": candidate.substation.name or "",
        "region": "" if profile is None else profile.region,
        "odre_code": (
            "" if identity is None or identity.odre_code is None else identity.odre_code
        ),
        "rte7000_id": (
            ""
            if identity is None or identity.rte7000_id is None
            else identity.rte7000_id
        ),
        "cartostock_id": "" if identity is None else identity.cartostock_id,
        "voltage_kv": "" if voltage is None else f"{voltage:g}",
        "source_site_distance_km": f"{candidate.substation.distance_km:.2f}",
        "opportunity_class": screening.opportunity_class,
        "deep_dive_recommendation": screening.deep_dive_recommendation,
        "total_score": screening.total_score,
        "public_grid_evidence_score": dimensions.get("public_grid_evidence", 0),
        "source_completeness_score": (
            "" if profile is None else profile.source_completeness_score
        ),
        "regional_constraint_count": (
            "" if profile is None else profile.regional_constraint_count
        ),
        "battery_storage_kw_region": (
            "" if profile is None else profile.battery_storage_kw_region
        ),
        "battery_storage_kw_source_substation": (
            "" if profile is None else profile.battery_storage_kw_source_substation
        ),
        "latest_regional_load_date": (
            "" if profile is None else profile.latest_regional_load_date
        ),
        "seed_use": "site_finder_reference_substation",
    }


def _bundle_summary(result: PortfolioScreeningResult) -> dict[str, object]:
    shortlist = [
        screening
        for screening in result.ranked_sites
        if screening.deep_dive_recommendation in {"recommended", "conditional"}
    ]
    return {
        "package_type": "portfolio_screening_bundle_summary",
        "validation_depth": "geospatial_screening",
        "policy_version": result.policy_version,
        "site_count": len(result.ranked_sites),
        "candidate_count": len(result.candidate_assessments),
        "source_error_count": len(result.source_errors),
        "source_errors": dict(result.source_errors),
        "opportunity_class_counts": _count_values(
            (screening.opportunity_class for screening in result.ranked_sites),
            ("A", "B", "C", "D"),
        ),
        "deep_dive_recommendation_counts": _count_values(
            (
                screening.deep_dive_recommendation
                for screening in result.ranked_sites
            ),
            ("recommended", "conditional", "not_recommended"),
        ),
        "deep_dive_shortlist_count": len(shortlist),
        "pending_class_a_manual_review_count": sum(
            screening.opportunity_class == "A"
            and screening.manual_review_status == "pending"
            for screening in result.ranked_sites
        ),
        "deep_dive_shortlist_site_ids": [
            screening.site.client_site_id for screening in shortlist
        ],
        "site_finder_seed_count": len(_site_finder_seed_screenings(result)),
        "top_ranked_site": (
            None if not result.ranked_sites else _summary_site(result.ranked_sites[0])
        ),
    }


def _count_values(values: Iterable[str], expected: tuple[str, ...]) -> dict[str, int]:
    counts = dict.fromkeys(expected, 0)
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _summary_site(screening: SiteScreening) -> dict[str, object]:
    candidate = screening.best_candidate
    identity = None if candidate is None else candidate.identity
    return {
        "portfolio_rank": screening.portfolio_rank,
        "client_site_id": screening.site.client_site_id,
        "opportunity_class": screening.opportunity_class,
        "recommendation": screening.recommendation,
        "deep_dive_recommendation": screening.deep_dive_recommendation,
        "total_score": screening.total_score,
        "candidate_name": "" if candidate is None else candidate.substation.name or "",
        "candidate_distance_km": (
            None if candidate is None else round(candidate.substation.distance_km, 6)
        ),
        "candidate_rte7000_id": (
            ""
            if identity is None or identity.rte7000_id is None
            else identity.rte7000_id
        ),
    }


def _deep_dive_input_package(
    screening: SiteScreening, policy_version: str
) -> dict[str, object]:
    return {
        "package_type": "deep_dive_site_input",
        "validation_depth": "geospatial_screening",
        "policy_version": policy_version,
        "client_site_id": screening.site.client_site_id,
        "screening": {
            "portfolio_rank": screening.portfolio_rank,
            "opportunity_class": screening.opportunity_class,
            "recommendation": screening.recommendation,
            "deep_dive_recommendation": screening.deep_dive_recommendation,
            "evidence_confidence": screening.evidence_confidence,
            "total_score": screening.total_score,
            "next_action": screening.next_action,
            "manual_review_required": screening.manual_review_required,
            "manual_review_status": screening.manual_review_status,
        },
        "site": _json_value(screening.site),
        "candidate": _candidate_deep_dive_package(screening.best_candidate),
        "score_dimensions": _json_value(screening.dimensions),
        "strongest_positive_signals": list(screening.strongest_positive_signals),
        "likely_constraints": list(screening.likely_constraints),
        "missing_evidence": list(screening.missing_evidence),
        "public_grid_evidence": _json_value(
            None
            if screening.best_candidate is None
            else screening.best_candidate.public_evidence
        ),
        "manual_review": {
            "required": screening.manual_review_required,
            "status": screening.manual_review_status,
            "reviewer": screening.manual_review_reviewer,
            "reviewed_at_utc": screening.manual_reviewed_at_utc,
            "notes": screening.manual_review_notes,
        },
        "manual_validation_checklist": [
            "Confirm canonical RTE/Enedis node and voltage level.",
            "Confirm bay availability and feasible physical route.",
            "Map RTE7000 id to the power-flow bus before simulation.",
            "Replace public signals with operator or client-validated data before investment memo.",
        ],
        "prohibited_claims": [
            "guaranteed_connection_capacity",
            "official_connection_feasibility",
            "reserved_grid_capacity",
            "operator_validated_cost_or_delay",
        ],
    }


def _candidate_deep_dive_package(
    candidate: CandidateScreening | None,
) -> dict[str, object] | None:
    if candidate is None:
        return None
    identity = candidate.identity
    cartostock = candidate.cartostock
    return {
        "name": candidate.substation.name or "",
        "distance_km": round(candidate.substation.distance_km, 6),
        "voltage_kv": _candidate_voltage(candidate),
        "osm_type": candidate.substation.osm_type,
        "osm_id": candidate.substation.osm_id,
        "osm_reference": candidate.substation.reference or "",
        "osm_source_url": candidate.substation.source_url,
        "match_confidence": candidate.match_confidence,
        "match_method": candidate.match_method,
        "cartostock_id": "" if identity is None else identity.cartostock_id,
        "odre_code": (
            "" if identity is None or identity.odre_code is None else identity.odre_code
        ),
        "rte7000_id": (
            ""
            if identity is None or identity.rte7000_id is None
            else identity.rte7000_id
        ),
        "cartostock_gabarit": "" if cartostock is None else cartostock.gabarit or "",
        "cartostock_gabarit_substation_capacity": (
            "" if cartostock is None else cartostock.gabarit_substation_capacity or ""
        ),
        "cartostock_gabarit_zone_capacity": (
            "" if cartostock is None else cartostock.gabarit_zone_capacity or ""
        ),
    }


def _safe_filename(value: str) -> str:
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return filename or "site"


def _render_report(result: PortfolioScreeningResult) -> str:
    lines = [
        "# VoltPath - Portfolio Screening",
        "",
        "## Synthèse exécutive",
        "",
        (
            f"{len(result.ranked_sites)} sites analysés avec la politique "
            f"`{result.policy_version}` au niveau `geospatial_screening`."
        ),
        "",
        "| Rang | Site | Score | Classe | Action | Poste candidat | Distance | Preuve |",
        "|---:|---|---:|:---:|---|---|---:|---|",
    ]
    for screening in result.ranked_sites:
        candidate = screening.best_candidate
        name = "aucun" if candidate is None else candidate.substation.name or "sans nom"
        distance = (
            "-"
            if candidate is None
            else f"{candidate.substation.distance_km:.1f} km"
        )
        lines.append(
            f"| {screening.portfolio_rank} | {screening.site.client_site_id} | "
            f"{screening.total_score} | {screening.opportunity_class} | "
            f"{screening.recommendation} | {name} | {distance} | "
            f"{screening.evidence_confidence} |"
        )

    lines.extend(["", "## Recommended Deep Dive Shortlist", ""])
    shortlist = tuple(
        screening
        for screening in result.ranked_sites
        if screening.deep_dive_recommendation in {"recommended", "conditional"}
    )
    if not shortlist:
        lines.append("No site currently justifies Deep Dive scoping.")
    else:
        lines.extend(
            [
                "| Rang | Site | Deep Dive | Classe | Score | Prochaine action |",
                "|---:|---|---|:---:|---:|---|",
            ]
        )
        for screening in shortlist:
            lines.append(
                f"| {screening.portfolio_rank} | {screening.site.client_site_id} | "
                f"{screening.deep_dive_recommendation} | {screening.opportunity_class} | "
                f"{screening.total_score} | {screening.next_action} |"
            )

    lines.extend(["", "## Mandatory Class A Review", ""])
    class_a = tuple(
        screening
        for screening in result.ranked_sites
        if screening.opportunity_class == "A"
    )
    if not class_a:
        lines.append("No Class A site requires review in this run.")
    else:
        lines.extend(
            [
                "| Site | Status | Reviewer | Reviewed at | Notes |",
                "|---|---|---|---|---|",
            ]
        )
        for screening in class_a:
            lines.append(
                f"| {screening.site.client_site_id} | "
                f"{screening.manual_review_status} | "
                f"{screening.manual_review_reviewer or '-'} | "
                f"{screening.manual_reviewed_at_utc or '-'} | "
                f"{screening.manual_review_notes or '-'} |"
            )

    lines.extend(
        [
            "",
            "## Public Evidence Boundary",
            "",
            (
                "ODRE and ECO2MIX are public-context evidence. They improve screening "
                "explainability but do not provide nodal measurements, reserved capacity, "
                "or official connection feasibility."
            ),
            "",
        ]
    )

    lines.extend(["", "## Détail des sites", ""])
    for screening in result.ranked_sites:
        lines.extend(_site_report_lines(screening))
    lines.extend(
        [
            "## Avertissements commerciaux",
            "",
            (
                "Cette analyse constitue une pré-faisabilité côté acheteur et ne "
                "remplace pas une étude officielle de raccordement, une PTF ou une "
                "offre RTE/Enedis."
            ),
            "",
            "- Les signaux Cartostock sont indicatifs et ne constituent ni réservation ni garantie.",
            "- La proximité géographique ne prouve pas la connectabilité électrique.",
            "- RTE7000 est une reconstruction publique, pas un modèle validé par l'opérateur.",
            "- Les coûts, délais, protections, courts-circuits, stabilité et disponibilité de cellule nécessitent une étude complémentaire.",
            "",
        ]
    )
    return "\n".join(lines)


def _site_report_lines(screening: SiteScreening) -> list[str]:
    candidate = screening.best_candidate
    candidate_label = (
        "aucun"
        if candidate is None
        else (
            f"{candidate.substation.name or 'sans nom'} à "
            f"{candidate.substation.distance_km:.1f} km"
        )
    )
    dimensions = ", ".join(
        f"{dimension.name}={dimension.points}/{dimension.maximum_points}"
        for dimension in screening.dimensions
    )
    positives = "; ".join(screening.strongest_positive_signals) or "aucun"
    constraints = "; ".join(screening.likely_constraints) or "aucune"
    missing = "; ".join(screening.missing_evidence) or "aucune"
    return [
        f"### {screening.portfolio_rank}. {screening.site.client_site_id}",
        "",
        f"- Décision de screening : **{screening.opportunity_class} / {screening.recommendation}**",
        f"- Poste candidat : {candidate_label}",
        f"- Décomposition du score : {dimensions}",
        f"- Signaux positifs : {positives}",
        f"- Contraintes probables : {constraints}",
        f"- Preuves manquantes : {missing}",
        f"- Recommandation Deep Dive : {screening.deep_dive_recommendation}",
        f"- Prochaine action : {screening.next_action}",
        "",
    ]


def _render_map(result: PortfolioScreeningResult) -> str:
    points: list[tuple[float, float, str, str]] = []
    for screening in result.ranked_sites:
        points.append(
            (
                screening.site.longitude,
                screening.site.latitude,
                screening.site.client_site_id,
                "site",
            )
        )
        candidate = screening.best_candidate
        if candidate is not None:
            points.append(
                (
                    candidate.substation.longitude,
                    candidate.substation.latitude,
                    candidate.substation.name or f"OSM {candidate.substation.osm_id}",
                    "substation",
                )
            )
    svg_points = _svg_points(points)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VoltPath Portfolio Screening Map</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; color: #172033; }}
.panel {{ max-width: 1000px; margin: auto; }}
svg {{ width: 100%; height: auto; border: 1px solid #cad2df; background: #f7f9fc; }}
.site {{ fill: #ec5b35; }}
.substation {{ fill: #2855d9; }}
text {{ font-size: 12px; fill: #172033; }}
.note {{ color: #5d6678; }}
</style>
</head>
<body>
<main class="panel">
<h1>VoltPath - Carte de situation</h1>
<p class="note">Projection relative sans fond cartographique. Les distances de décision
sont calculées par haversine; cette vue ne démontre pas la connectabilité électrique.</p>
<svg viewBox="0 0 900 500" role="img" aria-label="Sites et postes candidats">
{svg_points}
</svg>
<p><span class="site">●</span> Site client &nbsp;
<span class="substation">●</span> Poste candidat</p>
</main>
</body>
</html>
"""


def _svg_points(points: list[tuple[float, float, str, str]]) -> str:
    if not points:
        return '<text x="30" y="50">Aucun point géographique disponible.</text>'
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    min_lon, max_lon = min(longitudes), max(longitudes)
    min_lat, max_lat = min(latitudes), max(latitudes)
    lon_span = max(max_lon - min_lon, 0.01)
    lat_span = max(max_lat - min_lat, 0.01)
    rendered: list[str] = []
    for longitude, latitude, label, kind in points:
        x = 50.0 + ((longitude - min_lon) / lon_span) * 800.0
        y = 450.0 - ((latitude - min_lat) / lat_span) * 400.0
        safe_label = html.escape(label)
        rendered.append(
            f'<circle class="{kind}" cx="{x:.1f}" cy="{y:.1f}" r="7">'
            f"<title>{safe_label}</title></circle>"
        )
        rendered.append(
            f'<text x="{x + 10:.1f}" y="{y - 10:.1f}">{safe_label}</text>'
        )
    return "\n".join(rendered)


def _assumption_register(result: PortfolioScreeningResult) -> dict[str, object]:
    return {
        "policy_version": result.policy_version,
        "validation_depth": "geospatial_screening",
        "sources": {
            "cartostock": {
                "role": "indicative_public_signal",
                "limitations": "Not guaranteed connection capacity.",
            },
            "odre": {
                "role": "public_substation_identity",
                "limitations": "Public registry, not a connection offer.",
            },
            "rte7000": {
                "role": "public_reconstructed_topology",
                "limitations": "Reconstructed network, not operator-validated.",
            },
            "openstreetmap": {
                "role": "geographic_context",
                "limitations": "Distance and visible infrastructure only.",
            },
        },
        "assumptions": [
            "Straight-line distance is a first-pass connection-practicality proxy.",
            "OSM voltage and operator tags can be incomplete or outdated.",
            "Cartostock gabarit signals are interpreted as indicative injection context.",
            "Class A requires a deterministic canonical identity and RTE7000 link.",
        ],
        "prohibited_claims": [
            "guaranteed_connection_capacity",
            "official_connection_feasibility",
            "reserved_grid_capacity",
            "operator_validated_cost_or_delay",
        ],
    }


def _data_quality_report(
    result: PortfolioScreeningResult,
    source_manifests: tuple[Any, ...],
) -> dict[str, object]:
    manifest_records = tuple(
        item for item in source_manifests if isinstance(item, Mapping)
    )
    class_a = tuple(
        screening
        for screening in result.ranked_sites
        if screening.opportunity_class == "A"
    )
    review_counts = _count_values(
        (screening.manual_review_status for screening in class_a),
        ("pending", "approved", "rejected"),
    )
    evidence_profiles = {
        (profile.client_site_id, profile.odre_code): profile
        for candidate in result.candidate_assessments
        if (profile := candidate.public_evidence) is not None
    }.values()
    intervals = sorted(
        {
            profile.eco2mix_source_interval_minutes
            for profile in evidence_profiles
            if profile.eco2mix_source_interval_minutes is not None
        }
    )
    source_traceability = {
        "source_count": len(manifest_records),
        "identified_source_count": sum(
            bool(
                item.get("path")
                or item.get("source_path")
                or item.get("source_url")
                or item.get("endpoint")
                or item.get("repository")
            )
            for item in manifest_records
        ),
        "dated_source_count": sum(
            bool(item.get("retrieved_at_utc") or item.get("publication_date"))
            for item in manifest_records
        ),
        "licensed_source_count": sum(
            bool(item.get("license_name") or item.get("attribution"))
            for item in manifest_records
        ),
        "pinned_or_hashed_source_count": sum(
            bool(item.get("sha256") or item.get("revision") or item.get("query"))
            for item in manifest_records
        ),
    }
    source_traceability["complete"] = all(
        source_traceability[key] == source_traceability["source_count"]
        for key in (
            "identified_source_count",
            "dated_source_count",
            "licensed_source_count",
            "pinned_or_hashed_source_count",
        )
    )
    delivery_gate_passed = (
        review_counts["pending"] == 0 and review_counts["rejected"] == 0
    )
    overall_status = (
        "pass"
        if not result.source_errors
        and delivery_gate_passed
        and source_traceability["complete"]
        else "attention"
    )
    return {
        "policy_version": result.policy_version,
        "validation_depth": "geospatial_screening",
        "overall_status": overall_status,
        "source_traceability": source_traceability,
        "source_errors": dict(result.source_errors),
        "eco2mix": {
            "profile_count": len(evidence_profiles),
            "record_count": max(
                (profile.eco2mix_record_count for profile in evidence_profiles),
                default=0,
            ),
            "source_interval_minutes": intervals,
            "observed_consumption_count": max(
                (
                    profile.eco2mix_observed_consumption_count
                    for profile in evidence_profiles
                ),
                default=0,
            ),
            "missing_consumption_count": max(
                (
                    profile.eco2mix_missing_consumption_count
                    for profile in evidence_profiles
                ),
                default=0,
            ),
            "coverage_hours": max(
                (profile.eco2mix_coverage_hours for profile in evidence_profiles),
                default=0.0,
            ),
        },
        "identity": {
            "candidate_count": len(result.candidate_assessments),
            "match_confidence_counts": _count_values(
                (
                    candidate.match_confidence
                    for candidate in result.candidate_assessments
                ),
                ("exact", "high", "unmatched"),
            ),
        },
        "manual_review": {
            "class_a_count": len(class_a),
            "pending_count": review_counts["pending"],
            "approved_count": review_counts["approved"],
            "rejected_count": review_counts["rejected"],
            "delivery_gate_passed": delivery_gate_passed,
        },
    }


def _candidate_voltage(candidate: CandidateScreening | None) -> float | None:
    if candidate is None:
        return None
    if candidate.identity is not None and candidate.identity.voltage_kv is not None:
        return candidate.identity.voltage_kv
    if candidate.substation.voltage_levels_kv:
        return max(candidate.substation.voltage_levels_kv)
    return None


def _json_value(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
