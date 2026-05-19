import csv
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from thesegrid.cli import main
from thesegrid.models import CurtailmentEstimate
from thesegrid.networks import load_network
from thesegrid.qsts import (
    QstsBusResult,
    QstsHourlyRecord,
    QstsRequest,
    QstsResult,
    _decision_confidence,
    _qsts_economics_proxy,
    _profile_time_steps,
    _recommended_next_action,
    _qsts_verdict,
    _validation_level,
    _to_hourly_profile,
    classify_incremental_violations,
    compare_qsts_envelopes,
    load_simbench_power_profiles,
    qsts_envelope_records,
    qsts_curtailment_estimate,
    run_qsts,
    select_top_buses_from_screening_csv,
    summarize_qsts_risk,
    summarize_qsts_envelope,
    write_qsts_outputs,
)


def test_select_top_buses_from_screening_csv_uses_rank_order(tmp_path):
    csv_path = tmp_path / "screening.csv"
    _write_screening_csv(
        csv_path,
        [
            {"rank": "2", "bus_id": "12", "firm_capacity_mw": "3.5", "conditional_capacity_mw": "4.5"},
            {"rank": "1", "bus_id": "10", "firm_capacity_mw": "5.0", "conditional_capacity_mw": "5.0"},
        ],
    )

    selected = select_top_buses_from_screening_csv(csv_path, top_n=1)

    assert len(selected) == 1
    assert selected[0].bus_id == 10
    assert selected[0].firm_capacity_mw == 5.0
    assert selected[0].conditional_capacity_mw == 5.0


def test_select_top_buses_from_screening_csv_can_force_bus_ids(tmp_path):
    csv_path = tmp_path / "screening.csv"
    _write_screening_csv(
        csv_path,
        [
            {"rank": "1", "bus_id": "10", "firm_capacity_mw": "5.0", "conditional_capacity_mw": "5.0"},
            {"rank": "2", "bus_id": "12", "firm_capacity_mw": "3.5", "conditional_capacity_mw": "4.5"},
            {"rank": "3", "bus_id": "14", "firm_capacity_mw": "2.0", "conditional_capacity_mw": "3.0"},
        ],
    )

    selected = select_top_buses_from_screening_csv(csv_path, top_n=1, bus_ids=(14, 12))

    assert [bus.bus_id for bus in selected] == [14, 12]
    assert [bus.rank for bus in selected] == [3, 2]


def test_select_top_buses_from_screening_csv_rejects_missing_forced_bus(tmp_path):
    csv_path = tmp_path / "screening.csv"
    _write_screening_csv(
        csv_path,
        [
            {"rank": "1", "bus_id": "10", "firm_capacity_mw": "5.0", "conditional_capacity_mw": "5.0"},
        ],
    )

    with pytest.raises(ValueError, match="bus_ids not found in screening_csv: 99"):
        select_top_buses_from_screening_csv(csv_path, top_n=1, bus_ids=(99,))


def test_load_simbench_power_profiles_requires_simbench_profiles():
    net = SimpleNamespace(load=pd.DataFrame(), sgen=pd.DataFrame(), gen=pd.DataFrame())

    with pytest.raises(ValueError, match="SimBench profiles"):
        load_simbench_power_profiles(net)


def test_qsts_curtailment_estimate_uses_worst_direction_per_timestamp():
    hourly = pd.DataFrame(
        {
            "timestamp": [0, 0, 1, 1],
            "direction": ["injection", "withdrawal", "injection", "withdrawal"],
            "curtailed_mw": [0.0, 1.0, 2.0, 0.0],
        }
    )

    estimate = qsts_curtailment_estimate(hourly, timestep_hours=1.0)

    assert estimate.expected_hours == 2
    assert estimate.expected_mwh == 3.0
    assert estimate.p50_mw == 1.5
    assert estimate.p90_mw == 1.9


def test_qsts_hourly_records_convert_to_public_envelope_records(tmp_path):
    result = _sample_qsts_result(tmp_path)

    records = qsts_envelope_records(result)

    assert len(records) == 3
    assert records[0].timestamp == "2026-01-01T00:00:00"
    assert records[0].bus_id == 21
    assert records[0].direction == "injection"
    assert records[0].allowed_mw == 3.0
    assert records[0].curtailed_mw == 2.0
    assert records[0].incremental_binding_constraint == "line[1] line.loading_percent"
    assert records[0].qsts_verdict_context == "go-with-conditions"


def test_qsts_envelope_summary_groups_by_month_hour_direction(tmp_path):
    result = _sample_qsts_result(tmp_path)
    records = qsts_envelope_records(result)

    summary = summarize_qsts_envelope(records)

    injection = next(row for row in summary if row.direction == "injection")
    assert injection.month == 1
    assert injection.hour == 0
    assert injection.bus_id == 21
    assert injection.allowed_mw_min == 3.0
    assert injection.allowed_mw_p50 == 4.0
    assert round(injection.allowed_mw_p90, 6) == 4.8
    assert injection.curtailed_mw_p50 == 1.0
    assert round(injection.curtailed_mw_p90, 6) == 1.8
    assert injection.dominant_incremental_constraint == "line[1] line.loading_percent"


def test_compare_qsts_envelopes_includes_static_rte_and_qsts_options(tmp_path):
    result = _sample_qsts_result(tmp_path)

    comparisons = compare_qsts_envelopes(result)

    names = {comparison.envelope_name for comparison in comparisons}
    assert names == {
        "firm-only",
        "static custom envelope",
        "RTE injection-gabarit",
        "RTE withdrawal-gabarit",
        "QSTS-derived envelope",
    }
    qsts = next(comparison for comparison in comparisons if comparison.envelope_name == "QSTS-derived envelope")
    assert qsts.bus_id == 21
    assert qsts.violation_hours == 1
    assert qsts.p90_curtailment_mw > 0.0


def test_qsts_verdict_requires_explicit_p90_and_mwh_tolerance_for_conditions():
    curtailment = CurtailmentEstimate(
        expected_hours=2,
        expected_mwh=3.0,
        p50_mw=1.5,
        p90_mw=1.9,
    )

    assert _qsts_verdict(curtailment, p90_tolerance_mw=0.0, mwh_tolerance=3.0) == "no-go"
    assert _qsts_verdict(curtailment, p90_tolerance_mw=2.0, mwh_tolerance=2.9) == "no-go"
    assert (
        _qsts_verdict(curtailment, p90_tolerance_mw=2.0, mwh_tolerance=3.0)
        == "go-with-conditions"
    )
    assert (
        _qsts_verdict(
            CurtailmentEstimate(expected_hours=0, expected_mwh=0.0, p50_mw=0.0, p90_mw=0.0),
            p90_tolerance_mw=0.0,
            mwh_tolerance=0.0,
        )
        == "go"
    )


def test_qsts_decision_policy_marks_short_qsts_as_non_final(tmp_path):
    short_request = QstsRequest(
        network_code="1-MV-rural--0-sw",
        screening_csv=tmp_path / "screening.csv",
        requested_mw=5.0,
        duration_hours=24,
        p90_curtailment_tolerance_mw=3.0,
        expected_curtailment_tolerance_mwh=60.0,
    )
    full_year_request = QstsRequest(
        network_code="1-MV-rural--0-sw",
        screening_csv=tmp_path / "screening.csv",
        requested_mw=5.0,
        p90_curtailment_tolerance_mw=3.0,
        expected_curtailment_tolerance_mwh=60.0,
    )

    assert _validation_level(short_request, evaluated_time_steps=24) == "qsts_short"
    assert _decision_confidence(short_request, evaluated_time_steps=24) == "low"
    assert (
        _recommended_next_action("go", "no_curtailment", short_request)
        == "run_full_year_validation"
    )
    assert _validation_level(full_year_request, evaluated_time_steps=8784) == "qsts_full_year"
    assert _decision_confidence(full_year_request, evaluated_time_steps=8784) == "high"
    assert (
        _recommended_next_action("go", "no_curtailment", full_year_request, evaluated_time_steps=8784)
        == "proceed_to_investor_memo"
    )


def test_qsts_decision_policy_flags_p90_zero_mwh_tail_risk(tmp_path):
    request = QstsRequest(
        network_code="1-MV-rural--0-sw",
        screening_csv=tmp_path / "screening.csv",
        requested_mw=5.0,
        p90_curtailment_tolerance_mw=3.0,
        expected_curtailment_tolerance_mwh=60.0,
    )

    assert (
        _qsts_verdict(
            CurtailmentEstimate(
                expected_hours=52,
                expected_mwh=120.977,
                p50_mw=0.0,
                p90_mw=0.0,
            ),
            p90_tolerance_mw=3.0,
            mwh_tolerance=60.0,
        )
        == "no-go"
    )
    assert (
        _recommended_next_action("no-go", "mwh_exceeds_tolerance", request, evaluated_time_steps=8784)
        == "reject_or_resize_connection"
    )


def test_qsts_risk_summary_reports_tail_risk_driver_and_events(tmp_path):
    result = _tail_risk_qsts_result(tmp_path)

    rows = summarize_qsts_risk(result)

    assert len(rows) == 1
    row = rows[0]
    assert row.bus_id == 31
    assert row.verdict_driver == "mwh_exceeds_tolerance"
    assert row.tail_risk_flag is True
    assert row.curtailment_hours == 2
    assert row.expected_curtailment_mwh == 3.0
    assert row.curtailment_p90_mw == 1.7
    assert row.curtailment_p95_mw == 1.85
    assert row.curtailment_p99_mw == 1.97
    assert row.curtailment_max_mw == 2.0
    assert row.max_event_hours == 2
    assert row.max_event_mwh == 3.0
    assert row.dominant_constraint == "line[2] line.loading_percent: count=2"


def test_qsts_risk_summary_distinguishes_p90_and_combined_drivers(tmp_path):
    p90_only = _tail_risk_qsts_result(
        tmp_path,
        p90_mw=1.7,
        expected_mwh=3.0,
        p90_tolerance=1.0,
        mwh_tolerance=3.0,
    )
    both = _tail_risk_qsts_result(
        tmp_path,
        p90_mw=1.7,
        expected_mwh=3.0,
        p90_tolerance=1.0,
        mwh_tolerance=2.0,
    )

    assert summarize_qsts_risk(p90_only)[0].verdict_driver == "p90_exceeds_tolerance"
    assert summarize_qsts_risk(both)[0].verdict_driver == "both_exceed"


def test_qsts_request_rejects_negative_p90_tolerance(tmp_path):
    with pytest.raises(ValueError, match="p90_curtailment_tolerance_mw"):
        QstsRequest(
            network_code="1-MV-rural--0-sw",
            screening_csv=tmp_path / "screening.csv",
            requested_mw=1.0,
            p90_curtailment_tolerance_mw=-0.1,
        )


def test_qsts_request_rejects_negative_expected_curtailment_tolerance(tmp_path):
    with pytest.raises(ValueError, match="expected_curtailment_tolerance_mwh"):
        QstsRequest(
            network_code="1-MV-rural--0-sw",
            screening_csv=tmp_path / "screening.csv",
            requested_mw=1.0,
            expected_curtailment_tolerance_mwh=-0.1,
        )


def test_to_hourly_profile_averages_four_subhourly_steps():
    profile = pd.DataFrame({0: [1.0, 2.0, 3.0, 4.0, 9.0, 11.0, 13.0, 15.0]})

    hourly = _to_hourly_profile(profile)

    assert hourly[0].tolist() == [2.5, 12.0]


def test_profile_time_steps_can_use_stratified_sampling_across_time_blocks():
    profiles = {
        "load_p": pd.DataFrame({0: [0.0] * 8760}),
        "load_q": pd.DataFrame(),
        "sgen_p": pd.DataFrame(),
        "sgen_q": pd.DataFrame(),
        "gen_p": pd.DataFrame(),
        "storage_p": pd.DataFrame(),
    }

    steps = _profile_time_steps(
        profiles,
        start_hour=0,
        duration_hours=8760,
        sample_every_n_hours=168,
        stratified_sample=True,
    )

    assert len(steps) == 84
    assert len(steps) == len(set(steps))
    assert {step % 24 for step in steps} == {0, 7, 10, 13, 17, 18, 21}


def test_classify_incremental_violations_ignores_pre_existing_unworsened_violation():
    baseline = {
        ("bus", 14, "bus.vm_pu.max"): 1.059,
    }
    candidate = {
        ("bus", 14, "bus.vm_pu.max"): 1.059,
    }

    result = classify_incremental_violations(candidate, baseline)

    assert result == ()


def test_classify_incremental_violations_reports_new_and_worsened_violations():
    baseline = {("bus", 14, "bus.vm_pu.max"): 1.059}
    candidate = {
        ("bus", 14, "bus.vm_pu.max"): 1.062,
        ("line", 1, "line.loading_percent"): 101.0,
    }

    result = classify_incremental_violations(candidate, baseline)

    assert result == (
        "worsened_by_candidate: bus[14] bus.vm_pu.max=1.062 baseline=1.059",
        "new_candidate_violation: line[1] line.loading_percent=101.000",
    )


def test_cli_qsts_refuses_toy_network(tmp_path):
    exit_code = main(
        [
            "qsts",
            "--network",
            "toy",
            "--screening-csv",
            str(tmp_path / "missing.csv"),
            "--requested-mw",
            "1.0",
            "--output",
            str(tmp_path),
        ]
    )

    assert exit_code == 2


def test_cli_qsts_accepts_time_window_options(tmp_path, monkeypatch):
    screening_csv = tmp_path / "screening.csv"
    _write_screening_csv(
        screening_csv,
        [
            {"rank": "1", "bus_id": "1", "firm_capacity_mw": "1.0", "conditional_capacity_mw": "1.0"},
        ],
    )
    net = load_network("toy")
    profiles = {
        "load_p": pd.DataFrame({0: [0.1, 0.2, 0.3]}),
        "load_q": pd.DataFrame({0: [0.01, 0.02, 0.03]}),
        "sgen_p": pd.DataFrame(),
        "sgen_q": pd.DataFrame(),
        "gen_p": pd.DataFrame(),
        "storage_p": pd.DataFrame(),
    }

    monkeypatch.setattr("thesegrid.qsts.load_network", lambda _network_code: net)
    monkeypatch.setattr("thesegrid.qsts.load_simbench_power_profiles", lambda _net: profiles)

    exit_code = main(
        [
            "qsts",
            "--network",
            "1-MV-rural--0-sw",
            "--screening-csv",
            str(screening_csv),
            "--requested-mw",
            "0.5",
            "--top-n",
            "1",
            "--start-hour",
            "1",
            "--duration-hours",
            "1",
            "--sample-every-n-hours",
            "1",
            "--stratified-sample",
            "--p90-curtailment-tolerance-mw",
            "0.25",
            "--expected-curtailment-tolerance-mwh",
            "2.5",
            "--output",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    summary = (tmp_path / "out" / "qsts_summary.md").read_text(encoding="utf-8")
    assert "p90_curtailment_tolerance_mw: 0.250" in summary
    assert "expected_curtailment_tolerance_mwh: 2.500" in summary
    assert "stratified_sample: True" in summary
    assert "sample_every_n_hours: 1" in summary


def test_cli_qsts_passes_constraint_settings(tmp_path, monkeypatch):
    captured = {}

    def fake_run_qsts(request, settings=None):
        captured["request"] = request
        captured["settings"] = settings
        return QstsResult(request=request, buses=())

    def fake_write_qsts_outputs(_result, output_dir, command=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(
            results_csv_path=output_dir / "qsts_results.csv",
            summary_path=output_dir / "qsts_summary.md",
        )

    monkeypatch.setattr("thesegrid.cli.run_qsts", fake_run_qsts)
    monkeypatch.setattr("thesegrid.cli.write_qsts_outputs", fake_write_qsts_outputs)

    exit_code = main(
        [
            "qsts",
            "--network",
            "1-MV-rural--0-sw",
            "--screening-csv",
            str(tmp_path / "screening.csv"),
            "--requested-mw",
            "0.5",
            "--voltage-min-pu",
            "0.94",
            "--voltage-max-pu",
            "1.06",
            "--max-loading-percent",
            "90",
            "--sample-every-n-hours",
            "3",
            "--stratified-sample",
            "--expected-curtailment-tolerance-mwh",
            "1.5",
            "--output",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    assert captured["request"].sample_every_n_hours == 3
    assert captured["request"].stratified_sample is True
    assert captured["request"].expected_curtailment_tolerance_mwh == 1.5
    assert captured["settings"].min_vm_pu == 0.94
    assert captured["settings"].max_vm_pu == 1.06
    assert captured["settings"].max_loading_percent == 90.0


def test_cli_qsts_accepts_forced_bus_ids(tmp_path, monkeypatch):
    captured = {}

    def fake_run_qsts(request, settings=None):
        captured["request"] = request
        return QstsResult(request=request, buses=())

    monkeypatch.setattr("thesegrid.cli.run_qsts", fake_run_qsts)

    exit_code = main(
        [
            "qsts",
            "--network",
            "1-MV-rural--0-sw",
            "--screening-csv",
            str(tmp_path / "screening.csv"),
            "--requested-mw",
            "0.5",
            "--top-n",
            "1",
            "--bus-ids",
            "31,14",
            "--output",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    assert captured["request"].bus_ids == (31, 14)


def test_run_qsts_writes_results_summary_and_bus_detail(tmp_path, monkeypatch):
    screening_csv = tmp_path / "screening.csv"
    _write_screening_csv(
        screening_csv,
        [
            {"rank": "1", "bus_id": "1", "firm_capacity_mw": "1.0", "conditional_capacity_mw": "1.0"},
        ],
    )
    net = load_network("toy")
    profiles = {
        "load_p": pd.DataFrame({0: [0.1, 0.2]}),
        "load_q": pd.DataFrame({0: [0.01, 0.02]}),
        "sgen_p": pd.DataFrame(),
        "sgen_q": pd.DataFrame(),
        "gen_p": pd.DataFrame(),
        "storage_p": pd.DataFrame(),
    }

    monkeypatch.setattr("thesegrid.qsts.load_network", lambda _network_code: net)
    monkeypatch.setattr("thesegrid.qsts.load_simbench_power_profiles", lambda _net: profiles)

    result = run_qsts(
        QstsRequest(
            network_code="1-MV-rural--0-sw",
            screening_csv=screening_csv,
            requested_mw=0.5,
            top_n=1,
        )
    )
    assert result.buses[0].hourly_records[0].max_vm_pu is not None
    assert result.buses[0].hourly_records[0].max_loading_percent is not None
    outputs = write_qsts_outputs(result, tmp_path / "qsts")

    assert outputs.results_csv_path.exists()
    assert outputs.summary_path.exists()
    assert outputs.run_manifest_path.exists()
    assert outputs.investment_memo_path.exists()
    assert outputs.performance_json_path.exists()
    assert outputs.static_vs_qsts_comparison_csv_path.exists()
    assert outputs.annual_validation_summary_path.exists()
    assert outputs.envelope_csv_path.exists()
    assert outputs.envelope_summary_csv_path.exists()
    assert outputs.contractual_envelope_csv_path.exists()
    assert outputs.investor_decision_csv_path.exists()
    assert outputs.risk_summary_csv_path.exists()
    assert outputs.risk_summary_json_path.exists()
    assert outputs.bus_detail_paths == (tmp_path / "qsts" / "qsts_bus_1.csv",)
    with outputs.results_csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["bus_id"] == "1"
    assert rows[0]["qsts_verdict"] == "go"
    assert rows[0]["p90_curtailment_tolerance_mw"] == "0.000000"
    detail = outputs.bus_detail_paths[0].read_text(encoding="utf-8")
    assert "direction" in detail
    assert "incremental_binding_constraint" in detail
    assert "injection" in detail
    assert "withdrawal" in detail
    summary = outputs.summary_path.read_text(encoding="utf-8")
    assert "actual hourly power-flow validation" in summary
    assert "baseline-aware" in summary
    assert "Investor Decision Table" in summary
    assert (
        "| 1 | 1 | go | qsts_short | low | run_full_year_validation | "
        "1.000 | 1.000 | 0.000 | 0.000 | - |"
    ) in summary
    assert "Envelope Comparison" in summary
    assert "Contractual Envelope" in summary
    assert "QSTS-derived envelope" in summary
    assert "Risk Summary" in summary
    with outputs.envelope_csv_path.open(newline="", encoding="utf-8") as handle:
        envelope_rows = list(csv.DictReader(handle))
    assert envelope_rows[0]["allowed_mw"] == "0.500000"
    assert "qsts_verdict_context" in envelope_rows[0]
    with outputs.envelope_summary_csv_path.open(newline="", encoding="utf-8") as handle:
        summary_rows = list(csv.DictReader(handle))
    assert summary_rows[0]["direction"] in {"injection", "withdrawal"}
    assert "allowed_mw_p90" in summary_rows[0]
    with outputs.contractual_envelope_csv_path.open(newline="", encoding="utf-8") as handle:
        contractual_rows = list(csv.DictReader(handle))
    assert contractual_rows[0]["allowed_mw_p10"] == "0.500000"
    assert "curtailed_mw_p90" in contractual_rows[0]
    assert "allowed_mw_p25" in contractual_rows[0]
    with outputs.static_vs_qsts_comparison_csv_path.open(newline="", encoding="utf-8") as handle:
        comparison_rows = list(csv.DictReader(handle))
    assert comparison_rows[0]["bus_id"] == "1"
    assert comparison_rows[0]["contractual_allowed_mw_p25_min"] == "0.500000"
    annual_summary = outputs.annual_validation_summary_path.read_text(encoding="utf-8")
    assert "Annual Validation Summary" in annual_summary
    assert "static_vs_qsts_comparison.csv" in annual_summary
    with outputs.investor_decision_csv_path.open(newline="", encoding="utf-8") as handle:
        investor_rows = list(csv.DictReader(handle))
    assert investor_rows[0]["qsts_verdict"] == "go"
    assert investor_rows[0]["validation_level"] == "qsts_short"
    assert investor_rows[0]["decision_confidence"] == "low"
    assert investor_rows[0]["recommended_next_action"] == "run_full_year_validation"
    assert investor_rows[0]["qsts_p90_curtailment_mw"] == "0.000000"
    with outputs.risk_summary_csv_path.open(newline="", encoding="utf-8") as handle:
        risk_rows = list(csv.DictReader(handle))
    assert risk_rows[0]["verdict_driver"] == "no_curtailment"
    risk_json = json.loads(outputs.risk_summary_json_path.read_text(encoding="utf-8"))
    assert risk_json[0]["verdict_driver"] == "no_curtailment"
    assert risk_json[0]["tail_risk_flag"] is False
    manifest = outputs.run_manifest_path.read_text(encoding="utf-8")
    assert '"schema_version": "qsts-run-manifest-v1"' in manifest
    assert '"network_code": "1-MV-rural--0-sw"' in manifest
    assert '"contractual_envelope.csv"' in manifest
    assert '"qsts_performance.json"' in manifest
    assert '"qsts_risk_summary.csv"' in manifest
    performance = json.loads(outputs.performance_json_path.read_text(encoding="utf-8"))
    assert performance["evaluated_buses"] == 1
    assert performance["evaluated_time_steps"] == 2
    assert performance["evaluated_bus_hours"] == 2
    assert performance["power_flow_calls_per_bus_hour"] == 3.0
    assert performance["parallelization_unit"] == "bus"
    assert performance["baseline_power_flow_calls"] == 2
    assert performance["candidate_power_flow_calls"] == 4
    assert performance["power_flow_calls"] == 6
    memo = outputs.investment_memo_path.read_text(encoding="utf-8")
    assert "# QSTS BESS Investment Memo" in memo
    assert "Primary Recommendation" in memo
    assert "Decision Snapshot" in memo
    assert "validation_level: qsts_short" in memo
    assert "recommended_next_action: run_full_year_validation" in memo
    assert "Decision Drivers" in memo
    assert "risk rare but energetically material" in memo
    assert "Economics Proxy" in memo
    assert "proxy, not bankable revenue modelling" in memo
    assert "pré-faisabilité inspirée du cadre RTE/CRE" in memo
    assert "elle ne constitue pas une PTF ni une offre officielle RTE/Enedis" in memo
    assert "delta_npv_eur" in memo
    assert "discount_rate: 0.080" in memo
    assert "reinforcement_wait_years: 5.000" in memo
    assert "Three-Site Comparison" in memo
    assert "PTF" in memo
    assert "Contractual Envelope Summary" in memo
    assert "| 1 | 1 | go | 1.000 | 1.000 | 0.500 | 0.500 | 0.000 | 0.000 | - |" in memo
    summary = outputs.summary_path.read_text(encoding="utf-8")
    assert "validation_level: qsts_short" in summary
    assert "recommended_next_action" in summary
    annual_summary = outputs.annual_validation_summary_path.read_text(encoding="utf-8")
    assert "Validation Level" in annual_summary
    assert "qsts_short" in annual_summary


def test_qsts_request_rejects_negative_economic_inputs(tmp_path):
    with pytest.raises(ValueError, match="storage_duration_hours"):
        QstsRequest(
            network_code="1-MV-rural--0-sw",
            screening_csv=tmp_path / "screening.csv",
            requested_mw=1.0,
            storage_duration_hours=-1.0,
        )


def test_qsts_economics_proxy_exposes_waiting_and_discount_inputs(tmp_path):
    request = QstsRequest(
        network_code="1-MV-rural--0-sw",
        screening_csv=tmp_path / "screening.csv",
        requested_mw=2.0,
        storage_duration_hours=4.0,
        capex_eur_per_kw=100.0,
        fixed_opex_eur_per_kw_year=10.0,
        gross_revenue_eur_per_mw_year=50_000.0,
        curtailment_penalty_eur_per_mwh=100.0,
        reinforcement_wait_years=3.0,
        discount_rate=0.05,
    )
    result = _sample_qsts_result_for_request(request, verdict="go-with-conditions")

    economics = _qsts_economics_proxy(result)

    assert economics.reinforcement_wait_years == 3.0
    assert economics.discount_rate == 0.05
    assert economics.capex_eur == 200_000.0
    assert economics.annual_fixed_opex_eur == 20_000.0
    assert economics.annual_gross_revenue_eur == 100_000.0
    with pytest.raises(ValueError, match="discount_rate"):
        QstsRequest(
            network_code="1-MV-rural--0-sw",
            screening_csv=tmp_path / "screening.csv",
            requested_mw=1.0,
            discount_rate=-0.1,
        )


def test_cli_qsts_manifest_records_invocation(tmp_path, monkeypatch):
    captured = {}

    def fake_run_qsts(request, settings=None):
        captured["request"] = request
        return QstsResult(request=request, buses=())

    monkeypatch.setattr("thesegrid.cli.run_qsts", fake_run_qsts)

    output_dir = tmp_path / "out"
    exit_code = main(
        [
            "qsts",
            "--network",
            "1-MV-rural--0-sw",
            "--screening-csv",
            str(tmp_path / "screening.csv"),
            "--requested-mw",
            "0.5",
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    manifest = (output_dir / "run_manifest.json").read_text(encoding="utf-8")
    assert '"command": [' in manifest
    assert '"qsts"' in manifest
    assert '"--requested-mw"' in manifest
    assert '"0.5"' in manifest
    assert captured["request"].requested_mw == 0.5


def test_cli_qsts_accepts_progress_and_economics_options(tmp_path, monkeypatch):
    captured = {}

    def fake_run_qsts(request, settings=None):
        captured["request"] = request
        return QstsResult(request=request, buses=())

    monkeypatch.setattr("thesegrid.cli.run_qsts", fake_run_qsts)

    exit_code = main(
        [
            "qsts",
            "--network",
            "1-MV-rural--0-sw",
            "--screening-csv",
            str(tmp_path / "screening.csv"),
            "--requested-mw",
            "0.5",
            "--progress-every-n-hours",
            "250",
            "--storage-duration-hours",
            "4",
            "--capex-eur-per-kw",
            "250000",
            "--fixed-opex-eur-per-kw-year",
            "7000",
            "--gross-revenue-eur-per-mw-year",
            "120000",
            "--curtailment-penalty-eur-per-mwh",
            "150",
            "--reinforcement-wait-years",
            "6",
            "--discount-rate",
            "0.08",
            "--output",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    request = captured["request"]
    assert request.progress_every_n_hours == 250
    assert request.storage_duration_hours == 4.0
    assert request.capex_eur_per_kw == 250000.0
    assert request.fixed_opex_eur_per_kw_year == 7000.0
    assert request.gross_revenue_eur_per_mw_year == 120000.0
    assert request.curtailment_penalty_eur_per_mwh == 150.0
    assert request.reinforcement_wait_years == 6.0
    assert request.discount_rate == 0.08


def test_cli_qsts_sweep_writes_scenario_outputs_and_summary(tmp_path, monkeypatch):
    screening_csv = tmp_path / "screening.csv"
    _write_screening_csv(
        screening_csv,
        [
            {"rank": "1", "bus_id": "1", "firm_capacity_mw": "1.0", "conditional_capacity_mw": "1.0"},
        ],
    )
    config = tmp_path / "sweep.json"
    config.write_text(
        json.dumps(
            {
                "network_code": "1-MV-rural--0-sw",
                "screening_csv": str(screening_csv),
                "top_n": 1,
                "requested_mw": [0.5, 0.75],
                "p90_curtailment_tolerance_mw": [0.0],
                "expected_curtailment_tolerance_mwh": [0.0],
                "voltage_max_pu": [1.05],
                "sampling": "stratified",
            }
        ),
        encoding="utf-8",
    )

    def fake_run_qsts(request, settings=None):
        return _sample_qsts_result_for_request(request, verdict="go")

    monkeypatch.setattr("thesegrid.cli.run_qsts", fake_run_qsts)

    output = tmp_path / "sweep"
    exit_code = main(["qsts-sweep", "--config", str(config), "--output", str(output)])

    assert exit_code == 0
    assert (output / "sensitivity_results.csv").exists()
    assert (output / "sensitivity_summary.md").exists()
    assert (output / "sweep_manifest.json").exists()
    rows = list(csv.DictReader((output / "sensitivity_results.csv").open(encoding="utf-8")))
    assert [row["scenario_id"] for row in rows] == ["scenario_001", "scenario_002"]
    assert {row["requested_mw"] for row in rows} == {"0.500000", "0.750000"}
    assert (output / "scenario_001" / "qsts_performance.json").exists()


def test_cli_qsts_sweep_accepts_sampling_modes_and_writes_calibration(tmp_path, monkeypatch):
    screening_csv = tmp_path / "screening.csv"
    _write_screening_csv(
        screening_csv,
        [
            {"rank": "1", "bus_id": "1", "firm_capacity_mw": "1.0", "conditional_capacity_mw": "1.0"},
        ],
    )
    config = tmp_path / "sweep.json"
    config.write_text(
        json.dumps(
            {
                "network_code": "1-MV-rural--0-sw",
                "screening_csv": str(screening_csv),
                "top_n": 1,
                "requested_mw": [0.5],
                "p90_curtailment_tolerance_mw": [0.0],
                "expected_curtailment_tolerance_mwh": [0.0],
                "voltage_max_pu": [1.05],
                "sampling_modes": ["stratified", "full_year"],
                "start_hour": 1,
                "duration_hours": 2,
                "sample_every_n_hours": 2,
                "bus_ids": [1],
            }
        ),
        encoding="utf-8",
    )
    captured_requests = []

    def fake_run_qsts(request, settings=None):
        captured_requests.append(request)
        result = _sample_qsts_result_for_request(request, verdict="go")
        return QstsResult(
            request=result.request,
            buses=result.buses,
            performance=type(result.performance)(
                runtime_seconds=1.0,
                evaluated_time_steps=84 if request.stratified_sample else 8760,
                evaluated_buses=1,
            ),
        )

    monkeypatch.setattr("thesegrid.cli.run_qsts", fake_run_qsts)

    output = tmp_path / "sweep"
    exit_code = main(["qsts-sweep", "--config", str(config), "--output", str(output)])

    assert exit_code == 0
    rows = list(csv.DictReader((output / "sensitivity_results.csv").open(encoding="utf-8")))
    assert [row["sampling_mode"] for row in rows] == ["stratified", "full_year"]
    calibration = list(csv.DictReader((output / "sampling_calibration.csv").open(encoding="utf-8")))
    assert [row["sampling_mode"] for row in calibration] == ["stratified", "full_year"]
    assert calibration[0]["evaluated_hours"] == "84"
    assert calibration[1]["evaluated_hours"] == "8760"
    manifest = json.loads((output / "sweep_manifest.json").read_text(encoding="utf-8"))
    assert manifest["outputs"]["sampling_calibration"] == "sampling_calibration.csv"
    assert {request.start_hour for request in captured_requests} == {1}
    assert {request.duration_hours for request in captured_requests} == {2}
    assert {request.sample_every_n_hours for request in captured_requests} == {2}
    assert {request.bus_ids for request in captured_requests} == {(1,)}


def test_cli_qsts_sweep_rejects_invalid_config(tmp_path):
    config = tmp_path / "sweep.json"
    config.write_text('{"network_code": "1-MV-rural--0-sw"}', encoding="utf-8")

    exit_code = main(["qsts-sweep", "--config", str(config), "--output", str(tmp_path / "out")])

    assert exit_code == 2


def test_cli_qsts_resize_recommends_largest_acceptable_mw(tmp_path, monkeypatch):
    screening_csv = tmp_path / "screening.csv"
    _write_screening_csv(
        screening_csv,
        [
            {"rank": "1", "bus_id": "24", "firm_capacity_mw": "4.0", "conditional_capacity_mw": "4.0"},
        ],
    )
    requested_to_verdict = {
        5.0: ("no-go", 21932.0, 2.656),
        4.0: ("no-go", 11000.0, 1.5),
        3.0: ("no-go", 4399.0, 0.656),
        2.0: ("go-with-conditions", 19.8125, 0.0),
    }
    captured = []

    def fake_run_qsts(request, settings=None):
        captured.append(request.requested_mw)
        verdict, expected_mwh, p90_mw = requested_to_verdict[request.requested_mw]
        result = _sample_qsts_result_for_request(request, verdict=verdict)
        bus = result.buses[0]
        resized_bus = QstsBusResult(
            **{
                **bus.__dict__,
                "bus_id": 24,
                "bus_name": "bus-24",
                "qsts_verdict": verdict,
                "curtailment": CurtailmentEstimate(
                    expected_hours=13 if verdict != "no-go" else 8784,
                    expected_mwh=expected_mwh,
                    p50_mw=0.0,
                    p90_mw=p90_mw,
                ),
                "main_recurring_constraint": "bus[15] bus.vm_pu.max: count=9",
            }
        )
        return QstsResult(request=request, buses=(resized_bus,), performance=result.performance)

    monkeypatch.setattr("thesegrid.cli.run_qsts", fake_run_qsts)

    output = tmp_path / "resize"
    exit_code = main(
        [
            "qsts-resize",
            "--network",
            "1-MV-rural--0-sw",
            "--screening-csv",
            str(screening_csv),
            "--bus-id",
            "24",
            "--requested-mw",
            "5",
            "--min-mw",
            "2",
            "--step-mw",
            "1",
            "--p90-curtailment-tolerance-mw",
            "3",
            "--expected-curtailment-tolerance-mwh",
            "60",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert captured == [5.0, 4.0, 3.0, 2.0]
    rows = list(csv.DictReader((output / "resize_results.csv").open(encoding="utf-8")))
    assert rows[0]["product_decision"] == "no-go"
    assert rows[-1]["product_decision"] == "resize-recommended"
    assert rows[-1]["delta_mw_from_original"] == "3.000000"
    assert "delta_npv_eur" in rows[-1]
    assert rows[-1]["requested_mw"] == "2.000000"
    assert rows[-1]["qsts_verdict"] == "go-with-conditions"
    summary = (output / "resize_summary.md").read_text(encoding="utf-8")
    assert "product_decision: resize-recommended" in summary
    assert "recommended_resized_mw: 2.000" in summary
    assert "delta_mw_from_original: 3.000" in summary
    assert "Bus 24 is not acceptable at 5.000 MW" in summary
    assert "acceptable at 2.000 MW" in summary


def test_run_qsts_can_limit_time_window(tmp_path, monkeypatch):
    screening_csv = tmp_path / "screening.csv"
    _write_screening_csv(
        screening_csv,
        [
            {"rank": "1", "bus_id": "1", "firm_capacity_mw": "1.0", "conditional_capacity_mw": "1.0"},
        ],
    )
    net = load_network("toy")
    profiles = {
        "load_p": pd.DataFrame({0: [0.1, 0.2, 0.3, 0.4]}),
        "load_q": pd.DataFrame({0: [0.01, 0.02, 0.03, 0.04]}),
        "sgen_p": pd.DataFrame(),
        "sgen_q": pd.DataFrame(),
        "gen_p": pd.DataFrame(),
        "storage_p": pd.DataFrame(),
    }

    monkeypatch.setattr("thesegrid.qsts.load_network", lambda _network_code: net)
    monkeypatch.setattr("thesegrid.qsts.load_simbench_power_profiles", lambda _net: profiles)

    result = run_qsts(
        QstsRequest(
            network_code="1-MV-rural--0-sw",
            screening_csv=screening_csv,
            requested_mw=0.5,
            top_n=1,
            start_hour=1,
            duration_hours=2,
        )
    )

    assert [record.timestamp for record in result.buses[0].hourly_records] == [
        "2026-01-01T01:00:00",
        "2026-01-01T01:00:00",
        "2026-01-01T02:00:00",
        "2026-01-01T02:00:00",
    ]


def test_run_qsts_can_sample_every_n_hours(tmp_path, monkeypatch):
    screening_csv = tmp_path / "screening.csv"
    _write_screening_csv(
        screening_csv,
        [
            {"rank": "1", "bus_id": "1", "firm_capacity_mw": "1.0", "conditional_capacity_mw": "1.0"},
        ],
    )
    net = load_network("toy")
    profiles = {
        "load_p": pd.DataFrame({0: [0.1, 0.2, 0.3, 0.4]}),
        "load_q": pd.DataFrame({0: [0.01, 0.02, 0.03, 0.04]}),
        "sgen_p": pd.DataFrame(),
        "sgen_q": pd.DataFrame(),
        "gen_p": pd.DataFrame(),
        "storage_p": pd.DataFrame(),
    }

    monkeypatch.setattr("thesegrid.qsts.load_network", lambda _network_code: net)
    monkeypatch.setattr("thesegrid.qsts.load_simbench_power_profiles", lambda _net: profiles)

    result = run_qsts(
        QstsRequest(
            network_code="1-MV-rural--0-sw",
            screening_csv=screening_csv,
            requested_mw=0.5,
            top_n=1,
            sample_every_n_hours=2,
        )
    )

    assert [record.timestamp for record in result.buses[0].hourly_records] == [
        "2026-01-01T00:00:00",
        "2026-01-01T00:00:00",
        "2026-01-01T02:00:00",
        "2026-01-01T02:00:00",
    ]


def test_run_qsts_reuses_baseline_state_across_buses(tmp_path, monkeypatch):
    screening_csv = tmp_path / "screening.csv"
    _write_screening_csv(
        screening_csv,
        [
            {"rank": "1", "bus_id": "1", "firm_capacity_mw": "1.0", "conditional_capacity_mw": "1.0"},
            {"rank": "2", "bus_id": "1", "firm_capacity_mw": "1.0", "conditional_capacity_mw": "1.0"},
        ],
    )
    net = load_network("toy")
    profiles = {
        "load_p": pd.DataFrame({0: [0.1, 0.2]}),
        "load_q": pd.DataFrame({0: [0.01, 0.02]}),
        "sgen_p": pd.DataFrame(),
        "sgen_q": pd.DataFrame(),
        "gen_p": pd.DataFrame(),
        "storage_p": pd.DataFrame(),
    }
    calls = []
    real_baseline_state = __import__("thesegrid.qsts", fromlist=["_baseline_state"])._baseline_state

    def counting_baseline_state(net, bus_id, settings, tracker=None):
        calls.append(bus_id)
        return real_baseline_state(net, bus_id, settings, tracker)

    monkeypatch.setattr("thesegrid.qsts.load_network", lambda _network_code: net)
    monkeypatch.setattr("thesegrid.qsts.load_simbench_power_profiles", lambda _net: profiles)
    monkeypatch.setattr("thesegrid.qsts._baseline_state", counting_baseline_state)

    run_qsts(
        QstsRequest(
            network_code="1-MV-rural--0-sw",
            screening_csv=screening_csv,
            requested_mw=0.5,
            top_n=2,
        )
    )

    assert len(calls) == 2


def _sample_qsts_result(tmp_path):
    request = QstsRequest(
        network_code="1-MV-rural--0-sw",
        screening_csv=tmp_path / "screening.csv",
        requested_mw=5.0,
        top_n=1,
    )
    records = (
        QstsHourlyRecord(
            timestamp="2026-01-01T00:00:00",
            direction="injection",
            requested_mw=5.0,
            feasible_mw=3.0,
            curtailed_mw=2.0,
            converged=True,
            min_vm_pu=0.98,
            max_vm_pu=1.03,
            max_loading_percent=99.0,
            binding_constraint="line[1] line.loading_percent",
            incremental_binding_constraint="line[1] line.loading_percent",
        ),
        QstsHourlyRecord(
            timestamp="2026-01-01T00:30:00",
            direction="injection",
            requested_mw=5.0,
            feasible_mw=5.0,
            curtailed_mw=0.0,
            converged=True,
            min_vm_pu=0.98,
            max_vm_pu=1.02,
            max_loading_percent=80.0,
            binding_constraint="",
            incremental_binding_constraint="",
        ),
        QstsHourlyRecord(
            timestamp="2026-01-01T00:00:00",
            direction="withdrawal",
            requested_mw=5.0,
            feasible_mw=4.0,
            curtailed_mw=1.0,
            converged=True,
            min_vm_pu=0.95,
            max_vm_pu=1.01,
            max_loading_percent=70.0,
            binding_constraint="trafo[0] trafo.loading_percent",
            incremental_binding_constraint="trafo[0] trafo.loading_percent",
        ),
    )
    bus = QstsBusResult(
        rank=1,
        bus_id=21,
        bus_name="bus-21",
        qsts_verdict="go-with-conditions",
        requested_mw=5.0,
        static_firm_capacity_mw=4.0,
        static_conditional_capacity_mw=5.0,
        p90_curtailment_tolerance_mw=2.0,
        feasible_hours=1,
        violation_hours=1,
        curtailment=CurtailmentEstimate(
            expected_hours=1,
            expected_mwh=2.0,
            p50_mw=2.0,
            p90_mw=2.0,
        ),
        main_recurring_constraint="line[1] line.loading_percent: count=1",
        hourly_records=records,
    )
    return QstsResult(request=request, buses=(bus,))


def _sample_qsts_result_for_request(request, verdict):
    record = QstsHourlyRecord(
        timestamp="2026-01-01T00:00:00",
        direction="injection",
        requested_mw=request.requested_mw,
        feasible_mw=request.requested_mw,
        curtailed_mw=0.0,
        converged=True,
        min_vm_pu=0.98,
        max_vm_pu=1.02,
        max_loading_percent=70.0,
        binding_constraint="",
        incremental_binding_constraint="",
    )
    bus = QstsBusResult(
        rank=1,
        bus_id=1,
        bus_name="bus-1",
        qsts_verdict=verdict,
        requested_mw=request.requested_mw,
        static_firm_capacity_mw=request.requested_mw,
        static_conditional_capacity_mw=request.requested_mw,
        p90_curtailment_tolerance_mw=request.p90_curtailment_tolerance_mw,
        feasible_hours=1,
        violation_hours=0,
        curtailment=CurtailmentEstimate(
            expected_hours=0,
            expected_mwh=0.0,
            p50_mw=0.0,
            p90_mw=0.0,
        ),
        main_recurring_constraint="",
        hourly_records=(record,),
    )
    return QstsResult(request=request, buses=(bus,))


def _tail_risk_qsts_result(
    tmp_path,
    p90_mw=1.7,
    expected_mwh=3.0,
    p90_tolerance=2.0,
    mwh_tolerance=2.0,
):
    request = QstsRequest(
        network_code="1-MV-rural--0-sw",
        screening_csv=tmp_path / "screening.csv",
        requested_mw=5.0,
        top_n=1,
        p90_curtailment_tolerance_mw=p90_tolerance,
        expected_curtailment_tolerance_mwh=mwh_tolerance,
    )
    curtailments = [0.0, 1.0, 2.0, 0.0]
    records = tuple(
        QstsHourlyRecord(
            timestamp=f"2026-01-01T0{index}:00:00",
            direction="injection",
            requested_mw=5.0,
            feasible_mw=5.0 - curtailed,
            curtailed_mw=curtailed,
            converged=True,
            min_vm_pu=0.98,
            max_vm_pu=1.03,
            max_loading_percent=99.0,
            binding_constraint="line[2] line.loading_percent" if curtailed else "",
            incremental_binding_constraint="line[2] line.loading_percent" if curtailed else "",
        )
        for index, curtailed in enumerate(curtailments)
    )
    bus = QstsBusResult(
        rank=1,
        bus_id=31,
        bus_name="bus-31",
        qsts_verdict="no-go",
        requested_mw=5.0,
        static_firm_capacity_mw=5.0,
        static_conditional_capacity_mw=5.0,
        p90_curtailment_tolerance_mw=p90_tolerance,
        feasible_hours=2,
        violation_hours=2,
        curtailment=CurtailmentEstimate(
            expected_hours=2,
            expected_mwh=expected_mwh,
            p50_mw=0.5,
            p90_mw=p90_mw,
        ),
        main_recurring_constraint="line[2] line.loading_percent: count=2",
        hourly_records=records,
    )
    return QstsResult(request=request, buses=(bus,))


def _write_screening_csv(csv_path, rows):
    fieldnames = [
        "rank",
        "bus_id",
        "bus_name",
        "vn_kv",
        "verdict",
        "firm_injection_mw",
        "firm_withdrawal_mw",
        "firm_capacity_mw",
        "conditional_capacity_mw",
        "evaluated_conditional_mw",
        "recommended_envelope",
        "expected_curtailment_hours",
        "expected_curtailment_mwh",
        "p50_curtailment_mw",
        "p90_curtailment_mw",
        "ebitda_at_risk_eur",
        "flexible_value_delta_eur",
        "main_constraint",
    ]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "bus_name": f"bus-{row['bus_id']}",
                    "vn_kv": "20.0",
                    "verdict": "go",
                    "firm_injection_mw": row["firm_capacity_mw"],
                    "firm_withdrawal_mw": row["firm_capacity_mw"],
                    "evaluated_conditional_mw": row["conditional_capacity_mw"],
                    "recommended_envelope": "firm-only",
                    "expected_curtailment_hours": "0",
                    "expected_curtailment_mwh": "0.0",
                    "p50_curtailment_mw": "0.0",
                    "p90_curtailment_mw": "0.0",
                    "ebitda_at_risk_eur": "0.0",
                    "flexible_value_delta_eur": "1.0",
                    "main_constraint": "",
                    **row,
                }
            )
