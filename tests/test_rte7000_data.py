from __future__ import annotations

from datetime import UTC, datetime
import json
from dataclasses import asdict

import pandas as pd
import pytest

from thesegrid.rte7000_data import (
    Rte7000DataAccessError,
    Rte7000PartitionRequest,
    Rte7000SchemaError,
    read_rte7000_partition,
)


PINNED_REVISION = "1a2419a6f8a81ab212af035e811d4b893d7c4ccf"


def test_partition_request_builds_revision_pinned_hugging_face_path():
    request = Rte7000PartitionRequest(
        component="sub",
        year=2023,
        month=1,
        columns=("id", "name"),
        revision=PINNED_REVISION,
    )

    assert request.remote_path == (
        "hf://datasets/OpenSynth/rte7000@"
        f"{PINNED_REVISION}/sub/sub_2023-01.parquet"
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"component": "transformer"}, "component"),
        ({"revision": ""}, "revision"),
        ({"revision": "main"}, "immutable"),
        ({"year": 2020}, "year"),
        ({"month": 13}, "month"),
        ({"columns": ()}, "columns"),
        ({"columns": ("id", "id")}, "duplicate"),
    ],
)
def test_partition_request_rejects_invalid_values(overrides, message):
    values = {
        "component": "sub",
        "year": 2023,
        "month": 1,
        "columns": ("id", "name"),
        "revision": PINNED_REVISION,
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        Rte7000PartitionRequest(**values)


def test_read_partition_projects_columns_filters_rows_and_records_provenance():
    calls: list[
        tuple[str, tuple[str, ...], tuple[tuple[str, str, str], ...], str]
    ] = []

    def reader(
        path: str,
        *,
        columns: list[str],
        filters: list[tuple[str, str, str]],
        engine: str,
    ) -> pd.DataFrame:
        calls.append((path, tuple(columns), tuple(filters), engine))
        return pd.DataFrame(
            {
                "id": ["A", "C"],
                "name": ["Alpha", "Gamma"],
            }
        )

    request = Rte7000PartitionRequest(
        component="sub",
        year=2023,
        month=1,
        columns=("id", "name"),
        filters=(("region", "11"),),
        revision=PINNED_REVISION,
    )
    retrieved_at = datetime(2026, 6, 11, 12, 30, tzinfo=UTC)

    result = read_rte7000_partition(
        request,
        parquet_reader=reader,
        now=lambda: retrieved_at,
    )

    assert calls == [
        (
            request.remote_path,
            request.columns,
            (("region", "==", "11"),),
            "pyarrow",
        )
    ]
    assert result.frame.to_dict("records") == [
        {"id": "A", "name": "Alpha"},
        {"id": "C", "name": "Gamma"},
    ]
    assert result.manifest.repository == "OpenSynth/rte7000"
    assert result.manifest.revision == PINNED_REVISION
    assert result.manifest.remote_path == request.remote_path
    assert result.manifest.columns == request.columns
    assert result.manifest.filters == request.filters
    assert result.manifest.source_type == "public_reconstruction"
    assert result.manifest.row_count == 2
    assert result.manifest.retrieved_at_utc == "2026-06-11T12:30:00+00:00"


def test_read_partition_rejects_schema_drift():
    def reader(
        path: str,
        *,
        columns: list[str],
        filters: list[tuple[str, object]],
        engine: str,
    ) -> pd.DataFrame:
        del path, columns, filters, engine
        return pd.DataFrame({"id": ["A"]})

    request = Rte7000PartitionRequest(
        component="sub",
        year=2023,
        month=1,
        columns=("id", "name"),
        revision=PINNED_REVISION,
    )

    with pytest.raises(Rte7000SchemaError, match="name"):
        read_rte7000_partition(request, parquet_reader=reader)


def test_read_partition_wraps_remote_reader_failures():
    def reader(
        path: str,
        *,
        columns: list[str],
        filters: list[tuple[str, object]],
        engine: str,
    ) -> pd.DataFrame:
        del path, columns, filters, engine
        raise OSError("network unavailable")

    request = Rte7000PartitionRequest(
        component="bus",
        year=2022,
        month=12,
        columns=("id",),
        revision=PINNED_REVISION,
    )

    with pytest.raises(Rte7000DataAccessError, match="bus_2022-12.parquet"):
        read_rte7000_partition(request, parquet_reader=reader)


def test_partition_manifest_normalizes_timestamp_filters_for_json():
    def reader(
        path: str,
        *,
        columns: list[str],
        filters: list[tuple[str, str, object]],
        engine: str,
    ) -> pd.DataFrame:
        del path, columns, filters, engine
        return pd.DataFrame({"id": [".CTLH"]})

    request = Rte7000PartitionRequest(
        component="sub",
        year=2023,
        month=1,
        columns=("id",),
        filters=(("datetime", pd.Timestamp("2023-01-01 00:00:00")),),
        revision=PINNED_REVISION,
    )

    result = read_rte7000_partition(request, parquet_reader=reader)

    assert result.manifest.filters == (("datetime", "2023-01-01T00:00:00"),)
    json.dumps(asdict(result.manifest))
