from __future__ import annotations

import csv
import html
import json
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
    report_path: Path
    map_path: Path
    assumption_register_path: Path
    manifest_path: Path


def write_portfolio_screening_outputs(
    result: PortfolioScreeningResult,
    output_dir: Path,
    *,
    source_manifests: Iterable[object] = (),
    now: Clock | None = None,
) -> PortfolioScreeningOutputs:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = PortfolioScreeningOutputs(
        ranked_csv_path=output_dir / "portfolio_ranked.csv",
        candidates_csv_path=output_dir / "candidate_substations.csv",
        report_path=output_dir / "portfolio_screening_report.md",
        map_path=output_dir / "portfolio_screening_map.html",
        assumption_register_path=output_dir / "source_assumption_register.json",
        manifest_path=output_dir / "run_manifest.json",
    )
    _write_ranked_csv(result, outputs.ranked_csv_path)
    _write_candidates_csv(result, outputs.candidates_csv_path)
    outputs.report_path.write_text(_render_report(result), encoding="utf-8")
    outputs.map_path.write_text(_render_map(result), encoding="utf-8")
    outputs.assumption_register_path.write_text(
        json.dumps(_assumption_register(result), indent=2, ensure_ascii=False) + "\n",
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
        "source_manifests": [_json_value(item) for item in source_manifests],
        "outputs": {
            "ranked_portfolio": outputs.ranked_csv_path.name,
            "candidate_substations": outputs.candidates_csv_path.name,
            "report": outputs.report_path.name,
            "map": outputs.map_path.name,
            "assumption_register": outputs.assumption_register_path.name,
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
