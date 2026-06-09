import json

import pandas as pd

from thesegrid.ui_data import (
    best_resize_rows,
    discover_artifacts,
    load_result_bundle,
    manifest_context,
    verdict_counts,
)


def test_load_result_bundle_discovers_nested_pipeline_artifacts(tmp_path):
    root = tmp_path / "run"
    (root / "screening").mkdir(parents=True)
    (root / "validation").mkdir()
    (root / "qsts_full_year").mkdir()
    (root / "screening" / "screening.csv").write_text(
        "bus_id,verdict\n2,go\n21,no-go\n",
        encoding="utf-8",
    )
    (root / "validation" / "validation_matrix.csv").write_text(
        "bus_id,final_decision\n2,go\n21,no-go\n",
        encoding="utf-8",
    )
    (root / "qsts_full_year" / "qsts_performance.json").write_text(
        json.dumps({"runtime_seconds": 12.5}),
        encoding="utf-8",
    )

    bundle = load_result_bundle(root)

    assert bundle.artifacts["screening"] == root / "screening" / "screening.csv"
    assert bundle.artifacts["validation"] == root / "validation" / "validation_matrix.csv"
    assert bundle.json_payloads["performance"]["runtime_seconds"] == 12.5
    assert list(bundle.tables["screening"]["verdict"]) == ["go", "no-go"]


def test_discover_artifacts_supports_parallel_merged_outputs(tmp_path):
    merged = tmp_path / "merged"
    merged.mkdir()
    (merged / "qsts_results.csv").write_text("bus_id,qsts_verdict\n2,go\n", encoding="utf-8")
    (merged / "qsts_performance.json").write_text("{}", encoding="utf-8")

    artifacts = discover_artifacts(tmp_path)

    assert artifacts["qsts_full_year"] == merged / "qsts_results.csv"
    assert artifacts["performance"] == merged / "qsts_performance.json"


def test_best_resize_rows_keeps_largest_acceptable_mw_per_bus():
    frame = pd.DataFrame(
        [
            {"bus_id": 2, "requested_mw": "5.0", "acceptable": "False"},
            {"bus_id": 2, "requested_mw": "4.0", "acceptable": "True"},
            {"bus_id": 2, "requested_mw": "3.0", "acceptable": "True"},
            {"bus_id": 21, "requested_mw": "2.0", "acceptable": "True"},
        ]
    )

    best = best_resize_rows(frame)

    assert list(best["bus_id"]) == [2, 21]
    assert list(best["requested_mw"]) == ["4.0", "2.0"]


def test_verdict_counts_and_manifest_context_are_stable_for_missing_values():
    frame = pd.DataFrame({"final_decision": ["go", "no-go", "", None, "go"]})
    payload = {
        "request": {"network_code": "1-MV-rural--0-sw", "requested_mw": 5, "asset": "bess"},
        "evidence": {"evidence_level": "qsts_full_year", "decision_confidence": "high"},
    }

    assert verdict_counts(frame, "final_decision") == {"go": 2, "no-go": 1}
    assert manifest_context(payload) == {
        "network_code": "1-MV-rural--0-sw",
        "requested_mw": "5",
        "asset": "bess",
        "data_source_type": "",
        "evidence_level": "qsts_full_year",
        "decision_confidence": "high",
    }
