from pathlib import Path

from thesegrid.public_data.sources import LocalSourceManifest, local_source_manifest


def test_local_source_manifest_records_hash_size_and_role(tmp_path: Path):
    source = tmp_path / "sample.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    manifest = local_source_manifest(source, source_type="odre_constraints")

    assert isinstance(manifest, LocalSourceManifest)
    assert manifest.path == source
    assert manifest.source_type == "odre_constraints"
    assert manifest.size_bytes == source.stat().st_size
    assert len(manifest.sha256) == 64
    assert manifest.available is True
    assert manifest.error == ""


def test_missing_local_source_manifest_is_non_available(tmp_path: Path):
    manifest = local_source_manifest(tmp_path / "missing.csv", source_type="eco2mix")

    assert manifest.available is False
    assert manifest.size_bytes == 0
    assert manifest.sha256 == ""
    assert "missing" in manifest.error
