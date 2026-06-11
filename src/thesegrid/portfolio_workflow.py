from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from thesegrid.public_data.eco2mix import read_eco2mix_annual
from thesegrid.public_data.evidence import PublicGridEvidenceProfile, build_public_grid_evidence
from thesegrid.public_data.odre import (
    read_regional_constraints,
    read_regional_load_profiles,
    read_storage_assets,
)
from thesegrid.public_data.sources import local_source_manifest
from thesegrid.osm_substations import (
    OsmDataAccessError,
    OsmSchemaError,
    OsmSubstationResult,
    discover_osm_substations,
)
from thesegrid.portfolio_input import load_portfolio_sites
from thesegrid.portfolio_review import load_manual_reviews
from thesegrid.portfolio_reporting import (
    PortfolioScreeningOutputs,
    write_portfolio_screening_outputs,
)
from thesegrid.portfolio_screening import PortfolioScreeningResult, screen_portfolio
from thesegrid.rte7000_data import (
    Rte7000PartitionRequest,
    Rte7000PartitionResult,
    read_rte7000_partition,
)
from thesegrid.substation_identity import (
    OdreSubstationResult,
    build_french_substation_identities,
    link_osm_substation_identity,
    load_cartostock_substations,
    load_odre_substations,
)


OdreLoader = Callable[[], OdreSubstationResult]
RteReader = Callable[[Rte7000PartitionRequest], Rte7000PartitionResult]
OsmDiscoverer = Callable[..., OsmSubstationResult]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class PortfolioWorkflowRequest:
    portfolio_path: Path
    cartostock_path: Path
    output_dir: Path
    rte7000_revision: str
    rte7000_year: int = 2023
    rte7000_month: int = 1
    rte7000_snapshot: str = "2023-01-01T00:00:00"
    search_radius_km: float = 50.0
    osm_fixture_path: Path | None = None
    odre_substations_path: Path | None = None
    manual_reviews_path: Path | None = None
    odre_constraints_path: Path | None = None
    odre_storage_assets_path: Path | None = None
    odre_regional_loads_path: Path | None = None
    eco2mix_annual_path: Path | None = None

    def __post_init__(self) -> None:
        if not 1.0 <= self.search_radius_km <= 100.0:
            raise ValueError("search_radius_km must be between 1 and 100")
        _snapshot_datetime(self.rte7000_snapshot)


@dataclass(frozen=True)
class PortfolioWorkflowResult:
    screening: PortfolioScreeningResult
    outputs: PortfolioScreeningOutputs


@dataclass(frozen=True)
class PublicEvidenceBundle:
    profiles: tuple[PublicGridEvidenceProfile, ...]
    manifests: tuple[object, ...]


def run_portfolio_workflow(
    request: PortfolioWorkflowRequest,
    *,
    odre_loader: OdreLoader = load_odre_substations,
    rte_reader: RteReader = read_rte7000_partition,
    osm_discoverer: OsmDiscoverer = discover_osm_substations,
    now: Clock | None = None,
) -> PortfolioWorkflowResult:
    sites = load_portfolio_sites(request.portfolio_path)
    cartostock = load_cartostock_substations(request.cartostock_path)
    odre_result = (
        odre_loader()
        if request.odre_substations_path is None
        else load_odre_substations(source_path=request.odre_substations_path)
    )
    rte_result = rte_reader(
        Rte7000PartitionRequest(
            component="sub",
            year=request.rte7000_year,
            month=request.rte7000_month,
            columns=("id", "name"),
            revision=request.rte7000_revision,
            filters=(("datetime", _snapshot_datetime(request.rte7000_snapshot)),),
        )
    )
    identities = build_french_substation_identities(
        cartostock,
        odre_result.substations,
        rte_result.frame,
    )
    osm_fixtures = (
        None
        if request.osm_fixture_path is None
        else _load_osm_fixtures(request.osm_fixture_path)
    )

    links_by_site = {}
    source_errors: dict[str, str] = {}
    osm_manifests = []
    for site in sites:
        try:
            if osm_fixtures is None:
                osm_result = osm_discoverer(
                    site,
                    radius_km=request.search_radius_km,
                )
            else:
                osm_result = discover_osm_substations(
                    site,
                    radius_km=request.search_radius_km,
                    endpoint=f"fixture://{request.osm_fixture_path.name}",
                    fetcher=lambda _endpoint, _query, site_id=site.client_site_id: (
                        json.dumps(osm_fixtures[site_id]).encode()
                    ),
                )
        except (OsmDataAccessError, OsmSchemaError) as exc:
            source_errors[site.client_site_id] = str(exc)
            continue
        osm_manifests.append(osm_result.manifest)
        links_by_site[site.client_site_id] = tuple(
            link_osm_substation_identity(
                substation,
                identities,
                preferred_voltage_kv=site.preferred_voltage_kv,
            )
            for substation in osm_result.substations
        )

    public_evidence = _load_public_evidence_bundle(request, links_by_site)
    screening = screen_portfolio(
        sites,
        links_by_site,
        cartostock,
        source_errors=source_errors,
        public_evidence_profiles=public_evidence.profiles,
        manual_reviews=(
            {}
            if request.manual_reviews_path is None
            else load_manual_reviews(request.manual_reviews_path)
        ),
    )
    source_manifests = (
        _local_file_manifest(request.portfolio_path, "client_portfolio"),
        _local_file_manifest(request.cartostock_path, "cartostock_public_signal"),
        *(
            ()
            if request.osm_fixture_path is None
            else (
                _local_file_manifest(
                    request.osm_fixture_path,
                    "osm_overpass_fixture",
                ),
            )
        ),
        *(
            ()
            if request.manual_reviews_path is None
            else (
                _local_file_manifest(
                    request.manual_reviews_path,
                    "portfolio_manual_reviews",
                ),
            )
        ),
        odre_result.manifest,
        rte_result.manifest,
        *public_evidence.manifests,
        *osm_manifests,
    )
    outputs = write_portfolio_screening_outputs(
        screening,
        request.output_dir,
        source_manifests=source_manifests,
        now=now,
    )
    return PortfolioWorkflowResult(screening=screening, outputs=outputs)


def _load_public_evidence_bundle(
    request: PortfolioWorkflowRequest,
    links_by_site: dict[str, tuple[object, ...]],
) -> PublicEvidenceBundle:
    if (
        request.odre_constraints_path is None
        and request.odre_storage_assets_path is None
        and request.odre_regional_loads_path is None
        and request.eco2mix_annual_path is None
    ):
        return PublicEvidenceBundle((), ())
    manifests: list[object] = []

    constraints = None
    if request.odre_constraints_path is not None:
        if request.odre_constraints_path.exists():
            table = read_regional_constraints(request.odre_constraints_path)
            constraints = table.frame
            manifests.append(table.manifest)
        else:
            manifests.append(
                local_source_manifest(
                    request.odre_constraints_path,
                    "odre_regional_constraints",
                )
            )

    storage = None
    if request.odre_storage_assets_path is not None:
        if request.odre_storage_assets_path.exists():
            table = read_storage_assets(request.odre_storage_assets_path)
            storage = table.frame
            manifests.append(table.manifest)
        else:
            manifests.append(
                local_source_manifest(
                    request.odre_storage_assets_path,
                    "odre_storage_assets",
                )
            )

    eco2mix = None
    if request.eco2mix_annual_path is not None:
        if request.eco2mix_annual_path.exists():
            table = read_eco2mix_annual(request.eco2mix_annual_path)
            eco2mix = table.frame
            manifests.append(table.manifest)
        else:
            manifests.append(
                local_source_manifest(
                    request.eco2mix_annual_path,
                    "eco2mix_annual",
                )
            )

    regional_loads = None
    if request.odre_regional_loads_path is not None:
        if request.odre_regional_loads_path.exists():
            table = read_regional_load_profiles(request.odre_regional_loads_path)
            regional_loads = table.frame
            manifests.append(table.manifest)
        else:
            manifests.append(
                local_source_manifest(
                    request.odre_regional_loads_path,
                    "odre_regional_load_profiles",
                )
            )
    candidates: list[dict[str, str]] = []
    for site_id, links in links_by_site.items():
        for link in links:
            identity = getattr(link, "identity", None)
            odre_code = "" if identity is None or identity.odre_code is None else identity.odre_code
            if not odre_code:
                continue
            candidates.append(
                {
                    "client_site_id": site_id,
                    "region": _region_for_odre_code(odre_code, constraints, storage),
                    "odre_code": odre_code,
                }
            )
    if not candidates:
        return PublicEvidenceBundle((), tuple(manifests))
    return PublicEvidenceBundle(
        profiles=build_public_grid_evidence(
            site_candidates=candidates,
            regional_constraints=constraints,
            storage_assets=storage,
            regional_load_profiles=regional_loads,
            eco2mix_annual=eco2mix,
        ),
        manifests=tuple(manifests),
    )


def _region_for_odre_code(
    odre_code: str,
    regional_constraints: object,
    storage_assets: object,
) -> str:
    normalized_code = _normalize_public_code(odre_code)
    for frame, code_column in (
        (regional_constraints, "substation_1"),
        (storage_assets, "source_substation"),
    ):
        if frame is None or code_column not in frame or "region" not in frame:
            continue
        rows = frame[
            frame[code_column].astype(str).map(_normalize_public_code) == normalized_code
        ]
        if not rows.empty:
            return str(rows.iloc[0]["region"])
    return ""


def _normalize_public_code(value: object) -> str:
    return str(value).strip().upper().lstrip(".")


def _snapshot_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "rte7000_snapshot must be an ISO-8601 datetime"
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _local_file_manifest(path: Path, source_type: str) -> object:
    return local_source_manifest(path, source_type)


def _load_osm_fixtures(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid OSM fixture {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("OSM fixture must be an object keyed by client_site_id")
    return {str(site_id): payload for site_id, payload in document.items()}
