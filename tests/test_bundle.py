import csv
import json

from thesegrid.bundle import render_bundle_html, render_bundle_scorecard, write_bundle_report
from thesegrid.cli import main


def test_render_bundle_scorecard_summarizes_decision_evidence(tmp_path):
    bundle = _write_bundle(tmp_path)

    scorecard = render_bundle_scorecard(bundle)

    assert "MVP Evidence Scorecard" in scorecard
    assert "full_year_coverage: 3/3 buses" in scorecard
    assert "false_positive_stratified: 1" in scorecard
    assert "resize_recommendations: 1" in scorecard
    assert "readiness: demo_ready" in scorecard


def test_render_bundle_html_contains_tables_and_boundaries(tmp_path):
    bundle = _write_bundle(tmp_path)

    html = render_bundle_html(bundle)

    assert "<!doctype html>" in html
    assert "Thesegrid BESS Investor Evidence" in html
    assert "false_positive_stratified" in html
    assert "resize-recommended" in html
    assert "not an official grid-connection study" in html


def test_render_bundle_html_has_executive_summary_badges_and_artifact_links(tmp_path):
    bundle = _write_bundle(tmp_path)

    html = render_bundle_html(bundle)

    assert "Executive Summary" in html
    assert "Investment Decision" in html
    assert "class=\"badge badge-no-go\"" in html
    assert "class=\"badge badge-resize\"" in html
    assert "3/3 buses" in html
    assert "Open validation_matrix.csv" in html
    assert "Open resize_results.csv" in html
    assert "Open economic_scenarios.csv" in html
    assert "Open run_manifest.json" in html


def test_render_bundle_html_includes_proxy_economic_scenarios(tmp_path):
    bundle = _write_bundle(tmp_path)

    html = render_bundle_html(bundle)

    assert "Proxy Economics" in html
    assert "wait_for_reinforcement" in html
    assert "connect_now_5mw" in html
    assert "resize_bus24_2mw" in html
    assert "not bankable revenue modelling" in html


def test_write_bundle_report_creates_html_scorecard_and_campaign_guide(tmp_path):
    bundle = _write_bundle(tmp_path)

    outputs = write_bundle_report(bundle)

    assert outputs.html_path.exists()
    assert outputs.scorecard_path.exists()
    assert outputs.campaign_guide_path.exists()
    assert (bundle / "economic_scenarios.csv").exists()
    assert (bundle / "economic_scenarios.md").exists()
    assert "Next Calibration Campaign" in outputs.campaign_guide_path.read_text(encoding="utf-8")
    assert "Proxy Economic Scenarios" in (bundle / "economic_scenarios.md").read_text(
        encoding="utf-8"
    )


def test_render_bundle_cli_writes_proof_outputs(tmp_path):
    bundle = _write_bundle(tmp_path)

    exit_code = main(["render-bundle", "--bundle", str(bundle)])

    assert exit_code == 0
    assert (bundle / "investor_report.html").exists()
    assert (bundle / "scorecard.md").exists()
    assert (bundle / "next_calibration_campaign.md").exists()


def _write_bundle(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    _write_csv(
        bundle / "validation_matrix.csv",
        [
            "bus_id",
            "screening_verdict",
            "qsts_stratified_verdict",
            "qsts_full_year_verdict",
            "final_decision",
            "calibration_status",
            "recommended_next_action",
        ],
        [
            {
                "bus_id": "2",
                "screening_verdict": "go",
                "qsts_stratified_verdict": "go",
                "qsts_full_year_verdict": "no-go",
                "final_decision": "no-go",
                "calibration_status": "false_positive_stratified",
                "recommended_next_action": "reject_or_resize_connection",
            },
            {
                "bus_id": "21",
                "screening_verdict": "no-go",
                "qsts_stratified_verdict": "no-go",
                "qsts_full_year_verdict": "no-go",
                "final_decision": "no-go",
                "calibration_status": "changed_after_full_year",
                "recommended_next_action": "reject_or_resize_connection",
            },
            {
                "bus_id": "24",
                "screening_verdict": "no-go",
                "qsts_stratified_verdict": "no-go",
                "qsts_full_year_verdict": "no-go",
                "final_decision": "no-go",
                "calibration_status": "changed_after_full_year",
                "recommended_next_action": "reject_or_resize_connection",
            },
        ],
    )
    _write_csv(
        bundle / "resize_results.csv",
        [
            "scenario",
            "requested_mw",
            "qsts_verdict",
            "product_decision",
            "expected_curtailment_mwh",
            "p90_curtailment_mw",
        ],
        [
            {
                "scenario": "bus24_3mw",
                "requested_mw": "3.000000",
                "qsts_verdict": "no-go",
                "product_decision": "no-go",
                "expected_curtailment_mwh": "4399.781250",
                "p90_curtailment_mw": "0.656250",
            },
            {
                "scenario": "bus24_2mw",
                "requested_mw": "2.000000",
                "qsts_verdict": "go-with-conditions",
                "product_decision": "resize-recommended",
                "expected_curtailment_mwh": "19.812500",
                "p90_curtailment_mw": "0.000000",
            },
        ],
    )
    _write_csv(
        bundle / "qsts_results.csv",
        [
            "bus_id",
            "qsts_verdict",
            "requested_mw",
            "expected_curtailment_mwh",
            "p90_curtailment_mw",
        ],
        [
            {
                "bus_id": "2",
                "qsts_verdict": "no-go",
                "requested_mw": "5.000000",
                "expected_curtailment_mwh": "120.976562",
                "p90_curtailment_mw": "0.000000",
            }
        ],
    )
    (bundle / "qsts_performance.json").write_text(
        json.dumps({"total_full_year_runtime_seconds": 4418.49}),
        encoding="utf-8",
    )
    return bundle


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
