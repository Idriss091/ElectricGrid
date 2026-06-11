from pathlib import Path
from types import SimpleNamespace

import thesegrid.cli as cli_module
from thesegrid import ConnectionRequest, assess_connection
from thesegrid.cli import main
from thesegrid.memo import render_investment_memo
from thesegrid.networks import load_network


def test_assess_connection_produces_investment_memo_for_toy_network():
    request = ConnectionRequest(network_code="toy", bus_id=1, requested_mw=0.5)

    memo = assess_connection(request, net=load_network("toy"))

    assert memo.verdict == "go"
    assert memo.firm_injection_mw >= 0.45
    assert memo.firm_withdrawal_mw >= 0.45
    assert memo.recommended_envelope == "firm-only"


def test_render_investment_memo_includes_decision_assumptions_and_uncertainty():
    request = ConnectionRequest(network_code="toy", bus_id=1, requested_mw=0.5)
    memo = assess_connection(request, net=load_network("toy"))

    rendered = render_investment_memo(memo)

    assert "# Flexible Connection Pre-Feasibility Memo" in rendered
    assert "Verdict" in rendered
    assert "Assumptions" in rendered
    assert "Remaining Scientific Uncertainty" in rendered
    assert "does not replace an official grid-connection study" in rendered
    assert "pré-faisabilité inspirée du cadre RTE/CRE" in rendered
    assert "elle ne constitue pas une PTF ni une offre officielle RTE/Enedis" in rendered
    assert "evaluated_conditional_mw" in rendered
    assert "Envelope Comparison" in rendered


def test_assess_connection_reports_max_conditional_capacity_separately_from_request():
    request = ConnectionRequest(
        network_code="toy",
        bus_id=1,
        requested_mw=8.0,
        p90_curtailment_tolerance_mw=1.0,
    )

    memo = assess_connection(request, net=load_network("toy"))

    assert memo.evaluated_conditional_mw == 8.0
    assert memo.conditional_capacity_mw < request.requested_mw
    assert memo.conditional_capacity_mw > memo.firm_capacity_mw


def test_cli_assess_writes_reproducible_memo(tmp_path):
    output = tmp_path / "memo.md"

    exit_code = main(
        [
            "assess",
            "--network",
            "toy",
            "--bus",
            "1",
            "--requested-mw",
            "0.5",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()
    assert "network_code: toy" in Path(output).read_text()


def test_cli_portfolio_screen_runs_commercial_workflow(monkeypatch, tmp_path):
    portfolio = tmp_path / "portfolio.csv"
    cartostock = tmp_path / "cartostock.csv"
    fixture = tmp_path / "osm.json"
    output = tmp_path / "output"
    captured = {}

    def fake_run(request):
        captured["request"] = request
        output.mkdir()
        report = output / "portfolio_screening_report.md"
        manifest = output / "run_manifest.json"
        report.write_text("# report\n", encoding="utf-8")
        manifest.write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            screening=SimpleNamespace(ranked_sites=(object(), object())),
            outputs=SimpleNamespace(report_path=report, manifest_path=manifest),
        )

    monkeypatch.setattr(cli_module, "run_portfolio_workflow", fake_run)

    exit_code = main(
        [
            "portfolio-screen",
            "--portfolio",
            str(portfolio),
            "--cartostock",
            str(cartostock),
            "--output",
            str(output),
            "--rte7000-revision",
            "1a2419a6f8a81ab212af035e811d4b893d7c4ccf",
            "--rte7000-year",
            "2023",
            "--rte7000-month",
            "1",
            "--rte7000-snapshot",
            "2023-01-01T00:00:00",
            "--search-radius-km",
            "35",
            "--osm-fixture",
            str(fixture),
        ]
    )

    request = captured["request"]
    assert exit_code == 0
    assert request.portfolio_path == portfolio
    assert request.cartostock_path == cartostock
    assert request.output_dir == output
    assert request.rte7000_revision.startswith("1a2419")
    assert request.search_radius_km == 35.0
    assert request.osm_fixture_path == fixture
