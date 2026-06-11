from __future__ import annotations

import bz2
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DgittDownloader = Callable[..., str]
Clock = Callable[[], datetime]


class DgittDataAccessError(RuntimeError):
    """Raised when a targeted D-GITT snapshot cannot be acquired or verified."""


@dataclass(frozen=True)
class DgittSnapshotRequest:
    timestamp: datetime
    revision: str
    cache_dir: Path
    repository_owner: str = "OpenSynth"

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        timestamp = self.timestamp.astimezone(UTC)
        if timestamp.year not in {2021, 2022, 2023}:
            raise ValueError("D-GITT year must be between 2021 and 2023")
        if timestamp.minute % 5 or timestamp.second or timestamp.microsecond:
            raise ValueError("timestamp must align with the five-minute cadence")
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", self.revision):
            raise ValueError("revision must be an immutable Git commit SHA")
        if not self.repository_owner.strip():
            raise ValueError("repository_owner must not be empty")

    @property
    def timestamp_utc(self) -> datetime:
        return self.timestamp.astimezone(UTC)

    @property
    def repository(self) -> str:
        return (
            f"{self.repository_owner}/"
            f"D-GITT-RTE7000-{self.timestamp_utc.year}"
        )

    @property
    def remote_path(self) -> str:
        timestamp = self.timestamp_utc
        filename = (
            "recollement-auto-"
            f"{timestamp:%Y%m%d-%H%M}-enrichi.xiidm.bz2"
        )
        return f"{timestamp:%Y/%m/%d}/{filename}"


@dataclass(frozen=True)
class DgittSnapshotManifest:
    repository: str
    revision: str
    remote_path: str
    snapshot_timestamp_utc: str
    local_path: str
    size_bytes: int
    sha256: str
    retrieved_at_utc: str
    publisher: str = "OpenSynth"
    source_url: str = ""
    license_name: str = "CDLA-Permissive-2.0"
    source_type: str = "public_reconstruction"
    validation_level: str = "equipment"
    transformation_version: str = "dgitt-targeted-snapshot-v1"


@dataclass(frozen=True)
class DgittSnapshotResult:
    path: Path
    manifest: DgittSnapshotManifest


def fetch_dgitt_snapshot(
    request: DgittSnapshotRequest,
    *,
    downloader: DgittDownloader | None = None,
    now: Clock | None = None,
) -> DgittSnapshotResult:
    """Download and verify exactly one revision-pinned D-GITT XIIDM snapshot."""
    if downloader is None:
        from huggingface_hub import hf_hub_download

        downloader = hf_hub_download
    try:
        downloaded = downloader(
            repo_id=request.repository,
            repo_type="dataset",
            revision=request.revision,
            filename=request.remote_path,
            local_dir=request.cache_dir,
        )
    except Exception as exc:
        raise DgittDataAccessError(
            f"failed to acquire D-GITT snapshot "
            f"{request.repository}@{request.revision}/{request.remote_path}: {exc}"
        ) from exc
    path = Path(downloaded)
    try:
        payload_hash, size_bytes = _verify_bzip2_and_hash(path)
    except Exception as exc:
        raise DgittDataAccessError(
            f"corrupt D-GITT snapshot {path}: {exc}"
        ) from exc

    retrieved_at = (now or _utc_now)()
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    retrieved_at = retrieved_at.astimezone(UTC)
    manifest = DgittSnapshotManifest(
        repository=request.repository,
        revision=request.revision,
        remote_path=request.remote_path,
        snapshot_timestamp_utc=request.timestamp_utc.isoformat(),
        local_path=str(path),
        size_bytes=size_bytes,
        sha256=payload_hash,
        retrieved_at_utc=retrieved_at.isoformat(),
        source_url=f"https://huggingface.co/datasets/{request.repository}",
    )
    return DgittSnapshotResult(path=path, manifest=manifest)


def _verify_bzip2_and_hash(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size_bytes += len(chunk)
    with bz2.open(path, "rb") as handle:
        for _chunk in iter(lambda: handle.read(1024 * 1024), b""):
            pass
    return digest.hexdigest(), size_bytes


def _utc_now() -> datetime:
    return datetime.now(UTC)
