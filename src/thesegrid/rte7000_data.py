from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd


RTE7000_REPOSITORY = "OpenSynth/rte7000"
RTE7000_COMPONENTS = ("branch", "bus", "gen", "load", "sub", "switch", "vol")
RTE7000_YEARS = range(2021, 2024)

ParquetReader = Callable[..., pd.DataFrame]
Clock = Callable[[], datetime]


class Rte7000DataAccessError(RuntimeError):
    """Raised when a remote RTE7000 partition cannot be read."""


class Rte7000SchemaError(ValueError):
    """Raised when a remote partition does not contain the requested columns."""


@dataclass(frozen=True)
class Rte7000PartitionRequest:
    component: str
    year: int
    month: int
    columns: tuple[str, ...]
    revision: str
    filters: tuple[tuple[str, Any], ...] = ()
    repository: str = RTE7000_REPOSITORY

    def __post_init__(self) -> None:
        if self.component not in RTE7000_COMPONENTS:
            raise ValueError(
                "component must be one of: " + ", ".join(RTE7000_COMPONENTS)
            )
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", self.revision):
            raise ValueError("revision must be an immutable Git commit SHA")
        if self.year not in RTE7000_YEARS:
            raise ValueError("year must be between 2021 and 2023")
        if not 1 <= self.month <= 12:
            raise ValueError("month must be between 1 and 12")
        if not self.columns or any(not column for column in self.columns):
            raise ValueError("columns must contain at least one non-empty column")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("columns must not contain duplicate values")
        if any(not column for column, _value in self.filters):
            raise ValueError("filter columns must be non-empty")
        if not self.repository or "/" not in self.repository:
            raise ValueError("repository must use the Hugging Face owner/name format")

    @property
    def remote_path(self) -> str:
        filename = f"{self.component}_{self.year}-{self.month:02d}.parquet"
        return (
            f"hf://datasets/{self.repository}@{self.revision}/"
            f"{self.component}/{filename}"
        )


@dataclass(frozen=True)
class Rte7000PartitionManifest:
    repository: str
    revision: str
    remote_path: str
    component: str
    year: int
    month: int
    columns: tuple[str, ...]
    filters: tuple[tuple[str, Any], ...]
    source_type: str
    row_count: int
    retrieved_at_utc: str


@dataclass(frozen=True)
class Rte7000PartitionResult:
    frame: pd.DataFrame
    manifest: Rte7000PartitionManifest


def read_rte7000_partition(
    request: Rte7000PartitionRequest,
    *,
    parquet_reader: ParquetReader = pd.read_parquet,
    now: Clock | None = None,
) -> Rte7000PartitionResult:
    """Read one projected RTE7000 Parquet partition from a pinned Hub revision."""
    try:
        frame = parquet_reader(
            request.remote_path,
            columns=list(request.columns),
            filters=[
                (column, "==", value)
                for column, value in request.filters
            ],
            engine="pyarrow",
        )
    except Exception as exc:
        raise Rte7000DataAccessError(
            f"failed to read remote RTE7000 partition {request.remote_path}: {exc}"
        ) from exc

    missing_columns = [column for column in request.columns if column not in frame.columns]
    if missing_columns:
        raise Rte7000SchemaError(
            "remote RTE7000 partition is missing requested columns: "
            + ", ".join(missing_columns)
        )

    filtered = frame.loc[:, list(request.columns)].reset_index(drop=True)

    retrieved_at = (now or _utc_now)()
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    retrieved_at = retrieved_at.astimezone(UTC)

    manifest = Rte7000PartitionManifest(
        repository=request.repository,
        revision=request.revision,
        remote_path=request.remote_path,
        component=request.component,
        year=request.year,
        month=request.month,
        columns=request.columns,
        filters=tuple(
            (column, _manifest_value(value))
            for column, value in request.filters
        ),
        source_type="public_reconstruction",
        row_count=len(filtered),
        retrieved_at_utc=retrieved_at.isoformat(),
    )
    return Rte7000PartitionResult(frame=filtered, manifest=manifest)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _manifest_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
