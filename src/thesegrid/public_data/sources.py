from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class SourceMetadata:
    publisher: str
    source_url: str
    license_name: str
    transformation_version: str


SOURCE_METADATA: Mapping[str, SourceMetadata] = {
    "client_portfolio": SourceMetadata(
        publisher="Client",
        source_url="",
        license_name="Client-provided confidential data",
        transformation_version="portfolio-input-v1",
    ),
    "cartostock_public_signal": SourceMetadata(
        publisher="RTE",
        source_url="https://www.services-rte.com/",
        license_name="Licence Ouverte 2.0",
        transformation_version="cartostock-v1",
    ),
    "osm_overpass_fixture": SourceMetadata(
        publisher="OpenStreetMap contributors",
        source_url="https://www.openstreetmap.org/",
        license_name="ODbL 1.0",
        transformation_version="osm-overpass-v1",
    ),
    "portfolio_manual_reviews": SourceMetadata(
        publisher="VoltPath reviewer",
        source_url="",
        license_name="Client-confidential review record",
        transformation_version="portfolio-manual-review-v1",
    ),
    "commercial_interviews": SourceMetadata(
        publisher="VoltPath commercial validation",
        source_url="",
        license_name="Pseudonymized confidential research data",
        transformation_version="commercial-interviews-v1",
    ),
    "commercial_pilots": SourceMetadata(
        publisher="VoltPath commercial validation",
        source_url="",
        license_name="Pseudonymized confidential pilot data",
        transformation_version="commercial-pilots-v1",
    ),
    "commercial_ground_truth": SourceMetadata(
        publisher="VoltPath commercial validation",
        source_url="",
        license_name="Pseudonymized confidential calibration data",
        transformation_version="commercial-ground-truth-v1",
    ),
    "odre_regional_constraints": SourceMetadata(
        publisher="RTE / ODRÉ",
        source_url="https://odre.opendatasoft.com/",
        license_name="Licence Ouverte 2.0",
        transformation_version="odre-regional-constraints-v1",
    ),
    "odre_storage_assets": SourceMetadata(
        publisher="RTE / ODRÉ",
        source_url="https://odre.opendatasoft.com/",
        license_name="Licence Ouverte 2.0",
        transformation_version="odre-storage-assets-v1",
    ),
    "odre_regional_load_profiles": SourceMetadata(
        publisher="RTE / ODRÉ",
        source_url="https://odre.opendatasoft.com/",
        license_name="Licence Ouverte 2.0",
        transformation_version="odre-regional-load-profiles-v1",
    ),
    "eco2mix_annual": SourceMetadata(
        publisher="RTE",
        source_url="https://www.rte-france.com/eco2mix/telecharger-les-indicateurs",
        license_name="Licence Ouverte 2.0",
        transformation_version="eco2mix-annual-v1",
    ),
    "eco2mix_tempo": SourceMetadata(
        publisher="RTE",
        source_url="https://www.rte-france.com/eco2mix/telecharger-les-indicateurs",
        license_name="Licence Ouverte 2.0",
        transformation_version="eco2mix-tempo-v1",
    ),
}


@dataclass(frozen=True)
class LocalSourceManifest:
    path: Path
    source_type: str
    available: bool
    size_bytes: int
    sha256: str
    error: str = ""
    publisher: str = ""
    source_url: str = ""
    license_name: str = ""
    publication_date: str = ""
    publication_date_basis: str = ""
    retrieved_at_utc: str = ""
    file_modified_at_utc: str = ""
    transformation_version: str = ""
    row_count: int | None = None
    quality: Mapping[str, object] = field(default_factory=dict)


def local_source_manifest(
    path: Path,
    source_type: str,
    *,
    publisher: str | None = None,
    source_url: str | None = None,
    license_name: str | None = None,
    publication_date: str | None = None,
    transformation_version: str | None = None,
    row_count: int | None = None,
    quality: Mapping[str, object] | None = None,
    now: Clock | None = None,
) -> LocalSourceManifest:
    metadata = SOURCE_METADATA.get(
        source_type,
        SourceMetadata("", "", "", f"{source_type}-v1"),
    )
    retrieved_at = _as_utc((now or _utc_now)())
    common = {
        "publisher": metadata.publisher if publisher is None else publisher,
        "source_url": metadata.source_url if source_url is None else source_url,
        "license_name": (
            metadata.license_name if license_name is None else license_name
        ),
        "retrieved_at_utc": retrieved_at.isoformat(),
        "transformation_version": (
            metadata.transformation_version
            if transformation_version is None
            else transformation_version
        ),
        "row_count": row_count,
        "quality": dict(quality or {}),
    }
    if not path.exists():
        return LocalSourceManifest(
            path=path,
            source_type=source_type,
            available=False,
            size_bytes=0,
            sha256="",
            error=f"missing local source: {path}",
            publication_date=publication_date or "",
            publication_date_basis=(
                "provided" if publication_date else "unavailable"
            ),
            **common,
        )
    payload = path.read_bytes()
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return LocalSourceManifest(
        path=path,
        source_type=source_type,
        available=True,
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(payload).hexdigest(),
        publication_date=publication_date or modified_at.date().isoformat(),
        publication_date_basis=(
            "provided" if publication_date else "local_file_modified_at"
        ),
        file_modified_at_utc=modified_at.isoformat(),
        **common,
    )


def source_metadata(source_type: str) -> SourceMetadata:
    return SOURCE_METADATA.get(
        source_type,
        SourceMetadata("", "", "", f"{source_type}-v1"),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
