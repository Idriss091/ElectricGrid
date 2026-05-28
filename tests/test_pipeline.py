import json
from types import SimpleNamespace

from thesegrid.cli import main
from thesegrid.full_year_selection import FullYearCandidate
from thesegrid.pipeline import PipelineRequest, run_pipeline
from thesegrid.stratified_selection import StratifiedCandidate


def test_run_pipeline_writes_screening_selection_report_and_manifest(tmp_path):
    output = tmp_path / "pipeline"

    result = run_pipeline(
        PipelineRequest(
            network_code="toy",
            requested_mw=0.5,
            output_dir=output,
            max_buses=1,
            stratified_max_candidates=1,
            storage_duration_hours=4.0,
            round_trip_efficiency=0.9,
            soc_min_fraction=0.1,
            soc_max_fraction=0.9,
        )
    )

    assert result.report_path == output / "pipeline_report.md"
    assert result.manifest_path == output / "pipeline_manifest.json"
    assert result.screening_csv_path == output / "screening" / "screening.csv"
    assert result.stratified_selection_csv_path == output / "stratified_candidate_selection.csv"
    assert result.screening_csv_path.exists()
    assert result.stratified_selection_csv_path.exists()

    report = result.report_path.read_text(encoding="utf-8")
    assert "# Thesegrid Pipeline Report" in report
    assert "## Executive Summary" in report
    assert "evaluated_buses: 1" in report
    assert "stratified_shortlist_size: 1" in report
    assert "best_screening_bus:" in report
    assert "## Evidence Boundary" in report
    assert "## BESS-Lite Assumptions" in report
    assert "power_mw: 0.500" in report
    assert "duration_hours: 4.000" in report
    assert "nominal_energy_mwh: 2.000" in report
    assert "usable_energy_mwh: 1.600" in report
    assert "efficiency_adjusted_usable_energy_mwh: 1.440" in report
    assert "not a dispatch, degradation, revenue-stacking, or bankable valuation model" in report
    assert "network_code: toy" in report
    assert "screening_only" in report
    assert "data_source_type: benchmark" in report
    assert "decision_confidence: low" in report
    assert "recommended_next_action: run_qsts_validation" in report
    assert "## Stage Status" in report
    assert "| screening | completed | screening/screening.csv |" in report
    assert "| stratified_candidate_selection | completed | stratified_candidate_selection.csv |" in report
    assert "## Verdict Distribution" in report
    assert "| go | 1 |" in report
    assert "## Artifact Index" in report
    assert "pipeline_manifest.json" in report
    assert "screening/screening_summary.md" in report
    assert "## Recommended Next Actions" in report
    assert "QSTS was not run in this pipeline tranche" in report

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "thesegrid-pipeline-manifest-v1"
    assert manifest["request"]["network_code"] == "toy"
    assert manifest["request"]["requested_mw"] == 0.5
    assert manifest["evidence"]["evidence_level"] == "screening_only"
    assert manifest["evidence"]["data_source_type"] == "benchmark"
    assert manifest["evidence"]["decision_confidence"] == "low"
    assert manifest["bess_lite"]["power_mw"] == 0.5
    assert manifest["bess_lite"]["nominal_energy_mwh"] == 2.0
    assert manifest["bess_lite"]["usable_energy_mwh"] == 1.6
    assert manifest["stages"]["screening"]["status"] == "completed"
    assert manifest["stages"]["stratified_selection"]["status"] == "completed"
    assert manifest["stages"]["qsts_stratified"]["status"] == "not_run"


def test_cli_run_pipeline_writes_outputs(tmp_path):
    output = tmp_path / "cli-pipeline"

    exit_code = main(
        [
            "run-pipeline",
            "--network",
            "toy",
            "--requested-mw",
            "0.5",
            "--max-buses",
            "1",
            "--stratified-max-candidates",
            "1",
            "--storage-duration-hours",
            "3",
            "--data-source-type",
            "public_reconstruction",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert (output / "pipeline_report.md").exists()
    assert (output / "pipeline_manifest.json").exists()
    manifest = json.loads((output / "pipeline_manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence"]["data_source_type"] == "public_reconstruction"


def test_cli_run_pipeline_accepts_stratified_qsts_options(tmp_path, monkeypatch):
    captured = {}

    def fake_run_pipeline(request):
        captured["request"] = request
        return SimpleNamespace(
            report_path=tmp_path / "pipeline_report.md",
            manifest_path=tmp_path / "pipeline_manifest.json",
        )

    monkeypatch.setattr("thesegrid.cli.run_pipeline", fake_run_pipeline)

    exit_code = main(
        [
            "run-pipeline",
            "--network",
            "1-MV-rural--0-sw",
            "--requested-mw",
            "5",
            "--output",
            str(tmp_path / "pipeline"),
            "--run-qsts-stratified",
            "--run-qsts-full-year",
            "--qsts-duration-hours",
            "24",
            "--qsts-p90-curtailment-tolerance-mw",
            "3",
            "--qsts-expected-curtailment-tolerance-mwh",
            "60",
            "--qsts-voltage-max-pu",
            "1.04",
            "--full-year-max-candidates",
            "3",
            "--full-year-top-candidates",
            "1",
            "--full-year-borderline-candidates",
            "1",
            "--full-year-bad-controls",
            "1",
            "--run-resize-on-no-go",
            "--resize-min-mw",
            "2",
            "--resize-step-mw",
            "1",
            "--resize-selected-policy",
            "flexible",
        ]
    )

    assert exit_code == 0
    request = captured["request"]
    assert request.run_qsts_stratified is True
    assert request.run_qsts_full_year is True
    assert request.qsts_duration_hours == 24
    assert request.qsts_p90_curtailment_tolerance_mw == 3.0
    assert request.qsts_expected_curtailment_tolerance_mwh == 60.0
    assert request.qsts_voltage_max_pu == 1.04
    assert request.full_year_max_candidates == 3
    assert request.full_year_top_candidates == 1
    assert request.full_year_borderline_candidates == 1
    assert request.full_year_bad_controls == 1
    assert request.run_resize_on_no_go is True
    assert request.resize_min_mw == 2.0
    assert request.resize_step_mw == 1.0
    assert request.resize_selected_policy == "flexible"


def test_run_pipeline_rejects_full_year_without_stratified(tmp_path):
    try:
        PipelineRequest(
            network_code="1-MV-rural--0-sw",
            requested_mw=5.0,
            output_dir=tmp_path,
            run_qsts_full_year=True,
        )
    except ValueError as exc:
        assert "run_qsts_full_year requires run_qsts_stratified" in str(exc)
    else:
        raise AssertionError("expected PipelineRequest to reject full-year without stratified")


def test_run_pipeline_can_run_stratified_qsts_stage(tmp_path, monkeypatch):
    output = tmp_path / "pipeline"
    screening_csv = output / "screening" / "screening.csv"
    screening_summary = output / "screening" / "screening_summary.md"
    captured = {}

    row = SimpleNamespace(
        rank=1,
        bus_id=12,
        bus_name="MV bus 12",
        verdict="go",
        firm_capacity_mw=5.0,
        conditional_capacity_mw=5.0,
    )
    candidate = StratifiedCandidate(
        bus_id=12,
        bus_name="MV bus 12",
        selection_bucket="top_go",
        selection_reason="best screening go candidates",
        screening_rank=1,
        screening_verdict="go",
        firm_capacity_mw=5.0,
        conditional_capacity_mw=5.0,
        evaluated_conditional_mw=5.0,
        p90_curtailment_mw=0.0,
        main_constraint="",
    )

    def fake_write_screening_outputs(_result, _output_dir):
        screening_csv.parent.mkdir(parents=True, exist_ok=True)
        screening_csv.write_text("rank,bus_id\n1,12\n", encoding="utf-8")
        screening_summary.write_text("# screening\n", encoding="utf-8")
        return SimpleNamespace(csv_path=screening_csv, summary_path=screening_summary)

    def fake_run_qsts(request, settings):
        captured["qsts_request"] = request
        captured["qsts_settings"] = settings
        return SimpleNamespace()

    def fake_write_qsts_outputs(_result, output_dir, command):
        captured["qsts_command"] = tuple(command)
        output_dir.mkdir(parents=True, exist_ok=True)
        results = output_dir / "qsts_results.csv"
        summary = output_dir / "qsts_summary.md"
        manifest = output_dir / "run_manifest.json"
        memo = output_dir / "investment_memo.md"
        results.write_text("bus_id,qsts_verdict\n12,go\n", encoding="utf-8")
        summary.write_text("# qsts\n", encoding="utf-8")
        manifest.write_text("{}\n", encoding="utf-8")
        memo.write_text("# memo\n", encoding="utf-8")
        return SimpleNamespace(
            results_csv_path=results,
            summary_path=summary,
            run_manifest_path=manifest,
            investment_memo_path=memo,
        )

    def fake_select_full_year_candidates(request):
        captured["full_year_request"] = request
        return (
            FullYearCandidate(
                bus_id=12,
                bus_name="MV bus 12",
                requested_mw=5.0,
                selection_bucket="top_candidate",
                selection_reason="stratified go at highest tested MW",
                screening_rank=1,
                screening_verdict="go",
                stratified_verdict="go",
                stratified_p90_mw=0.0,
                stratified_expected_mwh=0.0,
            ),
        )

    def fake_write_full_year_selection_csv(candidates, output_path):
        captured["full_year_candidates"] = candidates
        output_path.write_text(
            "bus_id,bus_name,requested_mw,selection_bucket\n"
            "12,MV bus 12,5.0,top_candidate\n",
            encoding="utf-8",
        )
        return output_path

    monkeypatch.setattr(
        "thesegrid.pipeline.screen_connections",
        lambda _request: SimpleNamespace(rows=(row,)),
    )
    monkeypatch.setattr("thesegrid.pipeline.write_screening_outputs", fake_write_screening_outputs)
    monkeypatch.setattr(
        "thesegrid.pipeline.select_stratified_candidates",
        lambda _request: (candidate,),
    )
    monkeypatch.setattr("thesegrid.pipeline.run_qsts", fake_run_qsts)
    monkeypatch.setattr("thesegrid.pipeline.write_qsts_outputs", fake_write_qsts_outputs)
    monkeypatch.setattr(
        "thesegrid.pipeline.select_full_year_candidates",
        fake_select_full_year_candidates,
    )
    monkeypatch.setattr(
        "thesegrid.pipeline.write_full_year_selection_csv",
        fake_write_full_year_selection_csv,
    )

    result = run_pipeline(
        PipelineRequest(
            network_code="1-MV-rural--0-sw",
            requested_mw=5.0,
            output_dir=output,
            run_qsts_stratified=True,
            qsts_duration_hours=24,
            qsts_p90_curtailment_tolerance_mw=3.0,
            qsts_expected_curtailment_tolerance_mwh=60.0,
        )
    )

    assert result.qsts_stratified_results_csv_path == output / "qsts_stratified" / "qsts_results.csv"
    assert result.full_year_selection_csv_path == output / "full_year_candidate_selection.csv"
    assert captured["qsts_request"].bus_ids == (12,)
    assert captured["qsts_request"].stratified_sample is True
    assert captured["qsts_request"].duration_hours == 24
    assert captured["qsts_request"].p90_curtailment_tolerance_mw == 3.0
    assert captured["qsts_request"].expected_curtailment_tolerance_mwh == 60.0
    assert captured["qsts_command"] == ("run-pipeline", "qsts-stratified")
    assert captured["full_year_request"].screening_csv == screening_csv
    assert captured["full_year_request"].stratified_csv == result.qsts_stratified_results_csv_path
    assert captured["full_year_candidates"][0].bus_id == 12

    report = result.report_path.read_text(encoding="utf-8")
    assert "| qsts_stratified | completed | qsts_stratified/qsts_results.csv |" in report
    assert "| full_year_candidate_selection | completed | full_year_candidate_selection.csv |" in report
    assert "## Full-Year Candidate Selection" in report
    assert "| 12 | MV bus 12 | top_candidate | 5.000 |" in report
    assert "current_evidence_level: qsts_stratified" in report
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["evidence"]["evidence_level"] == "qsts_stratified"
    assert manifest["stages"]["qsts_stratified"]["status"] == "completed"
    assert manifest["stages"]["qsts_stratified"]["outputs"]["qsts_results"] == (
        "qsts_stratified/qsts_results.csv"
    )
    assert manifest["stages"]["full_year_selection"]["status"] == "completed"
    assert manifest["stages"]["full_year_selection"]["outputs"]["full_year_candidate_selection"] == (
        "full_year_candidate_selection.csv"
    )


def test_run_pipeline_can_run_full_year_qsts_stage(tmp_path, monkeypatch):
    output = tmp_path / "pipeline"
    screening_csv = output / "screening" / "screening.csv"
    screening_summary = output / "screening" / "screening_summary.md"
    captured = {"qsts_requests": [], "qsts_commands": []}

    row = SimpleNamespace(
        rank=1,
        bus_id=12,
        bus_name="MV bus 12",
        verdict="go",
        firm_capacity_mw=5.0,
        conditional_capacity_mw=5.0,
    )
    candidate = StratifiedCandidate(
        bus_id=12,
        bus_name="MV bus 12",
        selection_bucket="top_go",
        selection_reason="best screening go candidates",
        screening_rank=1,
        screening_verdict="go",
        firm_capacity_mw=5.0,
        conditional_capacity_mw=5.0,
        evaluated_conditional_mw=5.0,
        p90_curtailment_mw=0.0,
        main_constraint="",
    )
    full_year_candidate = FullYearCandidate(
        bus_id=12,
        bus_name="MV bus 12",
        requested_mw=5.0,
        selection_bucket="top_candidate",
        selection_reason="stratified go at highest tested MW",
        screening_rank=1,
        screening_verdict="go",
        stratified_verdict="go",
        stratified_p90_mw=0.0,
        stratified_expected_mwh=0.0,
    )

    def fake_write_screening_outputs(_result, _output_dir):
        screening_csv.parent.mkdir(parents=True, exist_ok=True)
        screening_csv.write_text("rank,bus_id\n1,12\n", encoding="utf-8")
        screening_summary.write_text("# screening\n", encoding="utf-8")
        return SimpleNamespace(csv_path=screening_csv, summary_path=screening_summary)

    def fake_run_qsts(request, settings):
        del settings
        captured["qsts_requests"].append(request)
        return SimpleNamespace()

    def fake_write_qsts_outputs(_result, output_dir, command):
        captured["qsts_commands"].append(tuple(command))
        output_dir.mkdir(parents=True, exist_ok=True)
        results = output_dir / "qsts_results.csv"
        summary = output_dir / "qsts_summary.md"
        manifest = output_dir / "run_manifest.json"
        memo = output_dir / "investment_memo.md"
        results.write_text("bus_id,qsts_verdict\n12,go\n", encoding="utf-8")
        summary.write_text("# qsts\n", encoding="utf-8")
        manifest.write_text("{}\n", encoding="utf-8")
        memo.write_text("# memo\n", encoding="utf-8")
        return SimpleNamespace(
            results_csv_path=results,
            summary_path=summary,
            run_manifest_path=manifest,
            investment_memo_path=memo,
        )

    monkeypatch.setattr(
        "thesegrid.pipeline.screen_connections",
        lambda _request: SimpleNamespace(rows=(row,)),
    )
    monkeypatch.setattr("thesegrid.pipeline.write_screening_outputs", fake_write_screening_outputs)
    monkeypatch.setattr(
        "thesegrid.pipeline.select_stratified_candidates",
        lambda _request: (candidate,),
    )
    monkeypatch.setattr("thesegrid.pipeline.run_qsts", fake_run_qsts)
    monkeypatch.setattr("thesegrid.pipeline.write_qsts_outputs", fake_write_qsts_outputs)
    monkeypatch.setattr(
        "thesegrid.pipeline.select_full_year_candidates",
        lambda _request: (full_year_candidate,),
    )
    monkeypatch.setattr(
        "thesegrid.pipeline.write_full_year_selection_csv",
        lambda _candidates, output_path: output_path.write_text("bus_id\n12\n", encoding="utf-8")
        or output_path,
    )

    result = run_pipeline(
        PipelineRequest(
            network_code="1-MV-rural--0-sw",
            requested_mw=5.0,
            output_dir=output,
            run_qsts_stratified=True,
            run_qsts_full_year=True,
            qsts_duration_hours=24,
            qsts_p90_curtailment_tolerance_mw=3.0,
            qsts_expected_curtailment_tolerance_mwh=60.0,
        )
    )

    assert result.qsts_full_year_results_csv_path == output / "qsts_full_year" / "qsts_results.csv"
    assert len(captured["qsts_requests"]) == 2
    assert captured["qsts_requests"][0].stratified_sample is True
    assert captured["qsts_requests"][0].duration_hours == 24
    assert captured["qsts_requests"][1].bus_ids == (12,)
    assert captured["qsts_requests"][1].stratified_sample is False
    assert captured["qsts_requests"][1].duration_hours is None
    assert captured["qsts_commands"] == [
        ("run-pipeline", "qsts-stratified"),
        ("run-pipeline", "qsts-full-year"),
    ]

    report = result.report_path.read_text(encoding="utf-8")
    assert "| qsts_full_year | completed | qsts_full_year/qsts_results.csv |" in report
    assert "current_evidence_level: qsts_full_year" in report
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["evidence"]["evidence_level"] == "qsts_full_year"
    assert manifest["stages"]["qsts_full_year"]["status"] == "completed"
    assert manifest["stages"]["qsts_full_year"]["outputs"]["qsts_results"] == (
        "qsts_full_year/qsts_results.csv"
    )


def test_run_pipeline_finishes_with_validation_matrix_and_bundle(tmp_path, monkeypatch):
    output = tmp_path / "pipeline"
    screening_csv = output / "screening" / "screening.csv"
    screening_summary = output / "screening" / "screening_summary.md"
    captured = {}

    row = SimpleNamespace(
        rank=1,
        bus_id=12,
        bus_name="MV bus 12",
        verdict="go",
        firm_capacity_mw=5.0,
        conditional_capacity_mw=5.0,
    )
    candidate = StratifiedCandidate(
        bus_id=12,
        bus_name="MV bus 12",
        selection_bucket="top_go",
        selection_reason="best screening go candidates",
        screening_rank=1,
        screening_verdict="go",
        firm_capacity_mw=5.0,
        conditional_capacity_mw=5.0,
        evaluated_conditional_mw=5.0,
        p90_curtailment_mw=0.0,
        main_constraint="",
    )
    full_year_candidate = FullYearCandidate(
        bus_id=12,
        bus_name="MV bus 12",
        requested_mw=5.0,
        selection_bucket="top_candidate",
        selection_reason="stratified go at highest tested MW",
        screening_rank=1,
        screening_verdict="go",
        stratified_verdict="go",
        stratified_p90_mw=0.0,
        stratified_expected_mwh=0.0,
    )

    def fake_write_screening_outputs(_result, _output_dir):
        screening_csv.parent.mkdir(parents=True, exist_ok=True)
        screening_csv.write_text("rank,bus_id,bus_name,verdict\n1,12,MV bus 12,go\n", encoding="utf-8")
        screening_summary.write_text("# screening\n", encoding="utf-8")
        return SimpleNamespace(csv_path=screening_csv, summary_path=screening_summary)

    def fake_write_qsts_outputs(_result, output_dir, command):
        del command
        output_dir.mkdir(parents=True, exist_ok=True)
        results = output_dir / "qsts_results.csv"
        performance = output_dir / "qsts_performance.json"
        frontier = output_dir / "decision_frontier.csv"
        results.write_text("bus_id,bus_name,qsts_verdict\n12,MV bus 12,go\n", encoding="utf-8")
        performance.write_text('{"runtime_seconds": 1.0}\n', encoding="utf-8")
        frontier.write_text("bus_id,policy,frontier_verdict\n12,standard,go\n", encoding="utf-8")
        return SimpleNamespace(
            results_csv_path=results,
            summary_path=output_dir / "qsts_summary.md",
            run_manifest_path=output_dir / "run_manifest.json",
            investment_memo_path=output_dir / "investment_memo.md",
            performance_json_path=performance,
            decision_frontier_csv_path=frontier,
        )

    def fake_build_validation_matrix(**kwargs):
        captured["validation_kwargs"] = kwargs
        return SimpleNamespace(rows=())

    def fake_write_validation_matrix_outputs(_matrix, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "validation_matrix.csv"
        markdown_path = output_dir / "validation_matrix.md"
        csv_path.write_text("bus_id,final_decision\n12,go\n", encoding="utf-8")
        markdown_path.write_text("# validation\n", encoding="utf-8")
        return SimpleNamespace(csv_path=csv_path, markdown_path=markdown_path)

    def fake_write_bundle_report(bundle_dir):
        captured["bundle_dir"] = bundle_dir
        html = bundle_dir / "investor_report.html"
        scorecard = bundle_dir / "scorecard.md"
        guide = bundle_dir / "next_calibration_campaign.md"
        html.write_text("<!doctype html>\n", encoding="utf-8")
        scorecard.write_text("# scorecard\n", encoding="utf-8")
        guide.write_text("# guide\n", encoding="utf-8")
        return SimpleNamespace(
            html_path=html,
            scorecard_path=scorecard,
            campaign_guide_path=guide,
        )

    monkeypatch.setattr(
        "thesegrid.pipeline.screen_connections",
        lambda _request: SimpleNamespace(rows=(row,)),
    )
    monkeypatch.setattr("thesegrid.pipeline.write_screening_outputs", fake_write_screening_outputs)
    monkeypatch.setattr(
        "thesegrid.pipeline.select_stratified_candidates",
        lambda _request: (candidate,),
    )
    monkeypatch.setattr("thesegrid.pipeline.run_qsts", lambda _request, settings: SimpleNamespace())
    monkeypatch.setattr("thesegrid.pipeline.write_qsts_outputs", fake_write_qsts_outputs)
    monkeypatch.setattr(
        "thesegrid.pipeline.select_full_year_candidates",
        lambda _request: (full_year_candidate,),
    )
    monkeypatch.setattr(
        "thesegrid.pipeline.write_full_year_selection_csv",
        lambda _candidates, output_path: output_path.write_text("bus_id\n12\n", encoding="utf-8")
        or output_path,
    )
    monkeypatch.setattr("thesegrid.pipeline.build_validation_matrix", fake_build_validation_matrix)
    monkeypatch.setattr(
        "thesegrid.pipeline.write_validation_matrix_outputs",
        fake_write_validation_matrix_outputs,
    )
    monkeypatch.setattr("thesegrid.pipeline.write_bundle_report", fake_write_bundle_report)

    result = run_pipeline(
        PipelineRequest(
            network_code="1-MV-rural--0-sw",
            requested_mw=5.0,
            output_dir=output,
            run_qsts_stratified=True,
            run_qsts_full_year=True,
        )
    )

    assert result.validation_matrix_csv_path == output / "validation" / "validation_matrix.csv"
    assert result.investor_report_html_path == output / "investor_report.html"
    assert captured["validation_kwargs"]["screening_csv"] == screening_csv
    assert captured["validation_kwargs"]["qsts_stratified_csv"] == (
        output / "qsts_stratified" / "qsts_results.csv"
    )
    assert captured["validation_kwargs"]["qsts_full_year_csvs"] == (
        output / "qsts_full_year" / "qsts_results.csv",
    )
    assert captured["bundle_dir"] == output
    assert (output / "validation_matrix.csv").exists()
    assert (output / "qsts_results.csv").exists()
    assert (output / "qsts_performance.json").exists()

    report = result.report_path.read_text(encoding="utf-8")
    assert "| validation_matrix | completed | validation/validation_matrix.csv |" in report
    assert "| investor_bundle | completed | investor_report.html |" in report
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stages"]["validation_matrix"]["status"] == "completed"
    assert manifest["stages"]["investor_bundle"]["status"] == "completed"


def test_run_pipeline_can_resize_full_year_no_go_finalists(tmp_path, monkeypatch):
    output = tmp_path / "pipeline"
    screening_csv = output / "screening" / "screening.csv"
    screening_summary = output / "screening" / "screening_summary.md"
    captured = {}

    row = SimpleNamespace(
        rank=1,
        bus_id=24,
        bus_name="MV bus 24",
        verdict="no-go",
        firm_capacity_mw=3.0,
        conditional_capacity_mw=3.0,
    )
    candidate = StratifiedCandidate(
        bus_id=24,
        bus_name="MV bus 24",
        selection_bucket="near_threshold_no_go",
        selection_reason="near threshold no-go candidates",
        screening_rank=1,
        screening_verdict="no-go",
        firm_capacity_mw=3.0,
        conditional_capacity_mw=3.0,
        evaluated_conditional_mw=5.0,
        p90_curtailment_mw=2.0,
        main_constraint="bus[15] vm_pu.max",
    )
    full_year_candidate = FullYearCandidate(
        bus_id=24,
        bus_name="MV bus 24",
        requested_mw=5.0,
        selection_bucket="bad_control",
        selection_reason="known bad control",
        screening_rank=1,
        screening_verdict="no-go",
        stratified_verdict="no-go",
        stratified_p90_mw=2.0,
        stratified_expected_mwh=200.0,
    )

    def fake_write_screening_outputs(_result, _output_dir):
        screening_csv.parent.mkdir(parents=True, exist_ok=True)
        screening_csv.write_text("rank,bus_id,bus_name,verdict\n1,24,MV bus 24,no-go\n", encoding="utf-8")
        screening_summary.write_text("# screening\n", encoding="utf-8")
        return SimpleNamespace(csv_path=screening_csv, summary_path=screening_summary)

    def fake_write_qsts_outputs(_result, output_dir, command):
        output_dir.mkdir(parents=True, exist_ok=True)
        verdict = "go" if command == ("run-pipeline", "qsts-stratified") else "no-go"
        results = output_dir / "qsts_results.csv"
        results.write_text(f"bus_id,bus_name,qsts_verdict\n24,MV bus 24,{verdict}\n", encoding="utf-8")
        performance = output_dir / "qsts_performance.json"
        frontier = output_dir / "decision_frontier.csv"
        performance.write_text('{"runtime_seconds": 1.0}\n', encoding="utf-8")
        frontier.write_text("bus_id,policy,frontier_verdict\n24,standard,no-go\n", encoding="utf-8")
        return SimpleNamespace(
            results_csv_path=results,
            summary_path=output_dir / "qsts_summary.md",
            run_manifest_path=output_dir / "run_manifest.json",
            investment_memo_path=output_dir / "investment_memo.md",
            performance_json_path=performance,
            decision_frontier_csv_path=frontier,
        )

    def fake_run_qsts(request, settings):
        del settings
        bus = SimpleNamespace(bus_id=24, bus_name="MV bus 24", qsts_verdict="no-go")
        return SimpleNamespace(request=request, buses=(bus,), performance=SimpleNamespace())

    def fake_run_resize_scenarios(request, settings):
        captured["resize_request"] = request
        captured["resize_settings"] = settings
        return SimpleNamespace(
            rows=(
                {
                    "bus_id": 24,
                    "requested_mw": "2.000000",
                    "original_requested_mw": "5.000000",
                    "product_decision": "resize-recommended",
                },
            )
        )

    def fake_write_resize_outputs(result, output_dir):
        captured["resize_result"] = result
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "resize_results.csv"
        summary_path = output_dir / "resize_summary.md"
        csv_path.write_text(
            "bus_id,requested_mw,original_requested_mw,product_decision\n"
            "24,2.000000,5.000000,resize-recommended\n",
            encoding="utf-8",
        )
        summary_path.write_text("# resize\n", encoding="utf-8")
        return SimpleNamespace(csv_path=csv_path, summary_path=summary_path)

    def fake_write_validation_matrix_outputs(_matrix, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "validation_matrix.csv"
        markdown_path = output_dir / "validation_matrix.md"
        csv_path.write_text("bus_id\n24\n", encoding="utf-8")
        markdown_path.write_text("# validation\n", encoding="utf-8")
        return SimpleNamespace(csv_path=csv_path, markdown_path=markdown_path)

    monkeypatch.setattr(
        "thesegrid.pipeline.screen_connections",
        lambda _request: SimpleNamespace(rows=(row,)),
    )
    monkeypatch.setattr("thesegrid.pipeline.write_screening_outputs", fake_write_screening_outputs)
    monkeypatch.setattr(
        "thesegrid.pipeline.select_stratified_candidates",
        lambda _request: (candidate,),
    )
    monkeypatch.setattr("thesegrid.pipeline.select_full_year_candidates", lambda _request: (full_year_candidate,))
    monkeypatch.setattr(
        "thesegrid.pipeline.write_full_year_selection_csv",
        lambda _candidates, output_path: output_path.write_text("bus_id\n24\n", encoding="utf-8")
        or output_path,
    )
    monkeypatch.setattr("thesegrid.pipeline.run_qsts", fake_run_qsts)
    monkeypatch.setattr("thesegrid.pipeline.write_qsts_outputs", fake_write_qsts_outputs)
    monkeypatch.setattr("thesegrid.pipeline.build_validation_matrix", lambda **_kwargs: SimpleNamespace(rows=()))
    monkeypatch.setattr(
        "thesegrid.pipeline.write_validation_matrix_outputs",
        fake_write_validation_matrix_outputs,
    )
    monkeypatch.setattr("thesegrid.pipeline.run_resize_scenarios", fake_run_resize_scenarios)
    monkeypatch.setattr("thesegrid.pipeline.write_resize_outputs", fake_write_resize_outputs)
    monkeypatch.setattr(
        "thesegrid.pipeline.write_bundle_report",
        lambda bundle_dir: SimpleNamespace(
            html_path=bundle_dir / "investor_report.html",
            scorecard_path=bundle_dir / "scorecard.md",
            campaign_guide_path=bundle_dir / "next_calibration_campaign.md",
        ),
    )

    result = run_pipeline(
        PipelineRequest(
            network_code="1-MV-rural--0-sw",
            requested_mw=5.0,
            output_dir=output,
            run_qsts_stratified=True,
            run_qsts_full_year=True,
            run_resize_on_no_go=True,
            resize_min_mw=2.0,
            resize_step_mw=1.0,
            resize_selected_policy="flexible",
        )
    )

    assert captured["resize_request"].bus_id == 24
    assert captured["resize_request"].original_requested_mw == 5.0
    assert captured["resize_request"].min_mw == 2.0
    assert captured["resize_request"].step_mw == 1.0
    assert captured["resize_request"].selected_policy == "flexible"
    assert result.resize_results_csv_path == output / "resize" / "resize_results.csv"
    assert (output / "resize_results.csv").exists()
    report = result.report_path.read_text(encoding="utf-8")
    assert "| resize | completed | resize/resize_results.csv |" in report
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stages"]["resize"]["status"] == "completed"
