import csv
from types import SimpleNamespace

import pandas as pd
import pytest

from thesegrid.cli import main
from thesegrid.networks import load_network
from thesegrid.qsts import (
    QstsRequest,
    _to_hourly_profile,
    load_simbench_power_profiles,
    qsts_curtailment_estimate,
    run_qsts,
    select_top_buses_from_screening_csv,
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


def test_to_hourly_profile_averages_four_subhourly_steps():
    profile = pd.DataFrame({0: [1.0, 2.0, 3.0, 4.0, 9.0, 11.0, 13.0, 15.0]})

    hourly = _to_hourly_profile(profile)

    assert hourly[0].tolist() == [2.5, 12.0]


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
    assert outputs.bus_detail_paths == (tmp_path / "qsts" / "qsts_bus_1.csv",)
    with outputs.results_csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["bus_id"] == "1"
    assert rows[0]["qsts_verdict"] == "go"
    detail = outputs.bus_detail_paths[0].read_text(encoding="utf-8")
    assert "direction" in detail
    assert "injection" in detail
    assert "withdrawal" in detail
    summary = outputs.summary_path.read_text(encoding="utf-8")
    assert "actual hourly power-flow validation" in summary


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
