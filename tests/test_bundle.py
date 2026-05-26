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
    assert "Benchmark Status" in html
    assert "SimBench benchmark network" in html


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


def test_render_bundle_html_includes_bus_power_decision_matrix_when_available(tmp_path):
    bundle = _write_bundle(tmp_path)
    _write_csv(
        bundle / "sensitivity_results.csv",
        [
            "bus_id",
            "bus_name",
            "qsts_verdict",
            "sampling_mode",
            "requested_mw",
            "qsts_p90_curtailment_mw",
            "qsts_expected_curtailment_mwh",
        ],
        [
            {
                "bus_id": "2",
                "bus_name": "MV bus 2",
                "qsts_verdict": "go",
                "sampling_mode": "stratified",
                "requested_mw": "2.000000",
                "qsts_p90_curtailment_mw": "0.000000",
                "qsts_expected_curtailment_mwh": "0.000000",
            },
            {
                "bus_id": "2",
                "bus_name": "MV bus 2",
                "qsts_verdict": "no-go",
                "sampling_mode": "stratified",
                "requested_mw": "5.000000",
                "qsts_p90_curtailment_mw": "0.000000",
                "qsts_expected_curtailment_mwh": "120.000000",
            },
            {
                "bus_id": "3",
                "bus_name": "MV bus 3",
                "qsts_verdict": "go",
                "sampling_mode": "stratified",
                "requested_mw": "7.000000",
                "qsts_p90_curtailment_mw": "0.000000",
                "qsts_expected_curtailment_mwh": "0.000000",
            },
        ],
    )

    html = render_bundle_html(bundle)

    assert "Decision Matrix" in html
    assert "stratified QSTS evidence" in html
    assert "Recommended MW by Bus" in html
    assert "2 MW" in html
    assert "5 MW" in html
    assert "MV bus 2" in html
    assert "P90 0.000000 MW / 120.000000 MWh" in html
    assert "7 MW" in html
    assert "run_full_year_validation" in html
    assert "Full-Year Conditional Checks" in html


def test_render_bundle_html_includes_targeted_full_year_conditional_checks(tmp_path):
    bundle = _write_bundle(tmp_path)
    _write_csv(
        bundle / "full_year_conditional_results.csv",
        [
            "bus_id",
            "bus_name",
            "qsts_verdict",
            "sampling_mode",
            "requested_mw",
            "qsts_p90_curtailment_mw",
            "qsts_expected_curtailment_mwh",
        ],
        [
            {
                "bus_id": "24",
                "bus_name": "MV bus 24",
                "qsts_verdict": "no-go",
                "sampling_mode": "full_year",
                "requested_mw": "3.000000",
                "qsts_p90_curtailment_mw": "0.656250",
                "qsts_expected_curtailment_mwh": "4399.781250",
            }
        ],
    )

    html = render_bundle_html(bundle)

    assert "Full-Year Conditional Checks" in html
    assert "MV bus 24" in html
    assert "4399.781250" in html


def test_render_bundle_html_includes_next_full_year_candidates_when_available(tmp_path):
    bundle = _write_bundle(tmp_path)
    _write_csv(
        bundle / "full_year_candidate_selection.csv",
        [
            "bus_id",
            "bus_name",
            "requested_mw",
            "selection_bucket",
            "selection_reason",
        ],
        [
            {
                "bus_id": "3",
                "bus_name": "MV bus 3",
                "requested_mw": "7.0",
                "selection_bucket": "top_candidate",
                "selection_reason": "stratified go at highest tested MW",
            }
        ],
    )

    html = render_bundle_html(bundle)

    assert "Next Full-Year Candidates" in html
    assert "top_candidate" in html
    assert "MV bus 3" in html


def test_render_bundle_html_includes_decision_frontier_for_full_year_rows(tmp_path):
    bundle = _write_bundle(tmp_path)
    _write_csv(
        bundle / "full_year_conditional_results.csv",
        [
            "bus_id",
            "bus_name",
            "qsts_verdict",
            "sampling_mode",
            "requested_mw",
            "qsts_p90_curtailment_mw",
            "qsts_expected_curtailment_mwh",
        ],
        [
            {
                "bus_id": "21",
                "bus_name": "MV bus 21",
                "qsts_verdict": "no-go",
                "sampling_mode": "full_year",
                "requested_mw": "3.000000",
                "qsts_p90_curtailment_mw": "0.187500",
                "qsts_expected_curtailment_mwh": "656.109375",
            }
        ],
    )

    html = render_bundle_html(bundle)

    assert "Decision Frontier" in html
    assert "curtailment_energy_ratio" in html
    assert "2.497%" in html
    assert "strict" in html
    assert "aggressive" in html


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
