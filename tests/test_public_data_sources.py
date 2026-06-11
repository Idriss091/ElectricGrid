from datetime import UTC, datetime
from pathlib import Path

from thesegrid.public_data.sources import LocalSourceManifest, local_source_manifest


def test_local_source_manifest_records_hash_size_and_role(tmp_path: Path):
    source = tmp_path / "sample.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    manifest = local_source_manifest(
        source,
        source_type="odre_constraints",
        publisher="RTE / ODRÉ",
        source_url="https://odre.opendatasoft.com/",
        license_name="Licence Ouverte 2.0",
        publication_date="2026-06-10",
        transformation_version="odre-constraints-v1",
        row_count=1,
        now=lambda: datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
    )

    assert isinstance(manifest, LocalSourceManifest)
    assert manifest.path == source
    assert manifest.source_type == "odre_constraints"
    assert manifest.size_bytes == source.stat().st_size
    assert len(manifest.sha256) == 64
    assert manifest.available is True
    assert manifest.error == ""
    assert manifest.publisher == "RTE / ODRÉ"
    assert manifest.source_url == "https://odre.opendatasoft.com/"
    assert manifest.license_name == "Licence Ouverte 2.0"
    assert manifest.publication_date == "2026-06-10"
    assert manifest.retrieved_at_utc == "2026-06-11T12:00:00+00:00"
    assert manifest.file_modified_at_utc
    assert manifest.transformation_version == "odre-constraints-v1"
    assert manifest.row_count == 1


def test_missing_local_source_manifest_is_non_available(tmp_path: Path):
    manifest = local_source_manifest(tmp_path / "missing.csv", source_type="eco2mix")

    assert manifest.available is False
    assert manifest.size_bytes == 0
    assert manifest.sha256 == ""
    assert "missing" in manifest.error
    assert manifest.retrieved_at_utc
    assert manifest.file_modified_at_utc == ""
