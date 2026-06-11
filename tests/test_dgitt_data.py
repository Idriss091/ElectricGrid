from __future__ import annotations

import bz2
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thesegrid.dgitt_data import (
    DgittDataAccessError,
    DgittSnapshotRequest,
    fetch_dgitt_snapshot,
)


REVISION = "77bfc432dd505f30a2a2fa79466680b614e3799c"


def test_snapshot_request_builds_pinned_five_minute_path(tmp_path: Path):
    request = DgittSnapshotRequest(
        timestamp=datetime(2023, 1, 1, 0, 5, tzinfo=UTC),
        revision=REVISION,
        cache_dir=tmp_path,
    )

    assert request.repository == "OpenSynth/D-GITT-RTE7000-2023"
    assert request.remote_path == (
        "2023/01/01/recollement-auto-20230101-0005-enrichi.xiidm.bz2"
    )


@pytest.mark.parametrize(
    ("timestamp", "revision", "message"),
    [
        (datetime(2020, 1, 1, tzinfo=UTC), REVISION, "year"),
        (datetime(2024, 1, 1, tzinfo=UTC), REVISION, "year"),
        (datetime(2023, 1, 1, 0, 1, tzinfo=UTC), REVISION, "five-minute"),
        (datetime(2023, 1, 1, tzinfo=UTC), "main", "immutable"),
    ],
)
def test_snapshot_request_rejects_invalid_scope(
    tmp_path: Path,
    timestamp: datetime,
    revision: str,
    message: str,
):
    with pytest.raises(ValueError, match=message):
        DgittSnapshotRequest(
            timestamp=timestamp,
            revision=revision,
            cache_dir=tmp_path,
        )


def test_fetch_snapshot_records_hash_size_and_provenance(tmp_path: Path):
    calls: list[dict[str, object]] = []
    payload = bz2.compress(b"<network id='fixture'/>")

    def downloader(**kwargs: object) -> str:
        calls.append(kwargs)
        path = tmp_path / "downloaded.xiidm.bz2"
        path.write_bytes(payload)
        return str(path)

    request = DgittSnapshotRequest(
        timestamp=datetime(2023, 1, 1, tzinfo=UTC),
        revision=REVISION,
        cache_dir=tmp_path / "cache",
    )
    result = fetch_dgitt_snapshot(
        request,
        downloader=downloader,
        now=lambda: datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
    )

    assert calls == [
        {
            "repo_id": request.repository,
            "repo_type": "dataset",
            "revision": REVISION,
            "filename": request.remote_path,
            "local_dir": request.cache_dir,
        }
    ]
    assert result.path == tmp_path / "downloaded.xiidm.bz2"
    assert result.manifest.repository == request.repository
    assert result.manifest.revision == REVISION
    assert result.manifest.remote_path == request.remote_path
    assert result.manifest.size_bytes == len(payload)
    assert len(result.manifest.sha256) == 64
    assert result.manifest.license_name == "CDLA-Permissive-2.0"
    assert result.manifest.retrieved_at_utc == "2026-06-11T12:00:00+00:00"


def test_fetch_snapshot_rejects_remote_and_corrupt_payloads(tmp_path: Path):
    request = DgittSnapshotRequest(
        timestamp=datetime(2023, 1, 1, tzinfo=UTC),
        revision=REVISION,
        cache_dir=tmp_path,
    )

    def unavailable(**kwargs: object) -> str:
        del kwargs
        raise OSError("offline")

    with pytest.raises(DgittDataAccessError, match="offline"):
        fetch_dgitt_snapshot(request, downloader=unavailable)

    corrupt = tmp_path / "corrupt.xiidm.bz2"
    corrupt.write_bytes(b"not-bzip2")

    def corrupt_downloader(**kwargs: object) -> str:
        del kwargs
        return str(corrupt)

    with pytest.raises(DgittDataAccessError, match="corrupt"):
        fetch_dgitt_snapshot(request, downloader=corrupt_downloader)
