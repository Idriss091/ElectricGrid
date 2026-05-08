import csv

from thesegrid.cli import main
from thesegrid.models import EconomicAssumptions
from thesegrid.screening import (
    ScreeningRequest,
    ScreeningRow,
    candidate_bus_ids,
    render_screening_summary,
    screen_connections,
    sort_screening_rows,
    write_screening_outputs,
)
from thesegrid.networks import ToyNetwork, load_network


def test_candidate_bus_ids_uses_toy_fallback_candidate():
    net = load_network("toy")

    assert candidate_bus_ids(net, "mv_active") == (1,)


def test_candidate_bus_ids_falls_back_to_non_slack_active_bus_when_no_mv_bus_matches():
    net = ToyNetwork(
        name="fallback",
        bus=load_network("toy").bus.assign(vn_kv=[110.0, 110.0], in_service=[True, True]),
    )

    assert candidate_bus_ids(net, "mv_active") == (1,)


def test_sort_screening_rows_prioritizes_verdict_value_capacity_and_risk():
    rows = (
        _row(bus_id=1, verdict="go-with-conditions", value=200.0, conditional=4.0, p90=0.1),
        _row(bus_id=2, verdict="go", value=10.0, conditional=1.0, p90=0.0),
        _row(bus_id=3, verdict="go-with-conditions", value=300.0, conditional=3.0, p90=0.2),
        _row(bus_id=4, verdict="no-go", value=10_000.0, conditional=10.0, p90=0.0),
    )

    ranked = sort_screening_rows(rows)

    assert [row.bus_id for row in ranked] == [2, 3, 1, 4]
    assert [row.rank for row in ranked] == [1, 2, 3, 4]


def test_screen_connections_returns_ranked_top_rows_for_toy_network():
    result = screen_connections(
        ScreeningRequest(
            network_code="toy",
            requested_mw=0.5,
            economics=EconomicAssumptions(waiting_cost_eur_per_mw_year=1.0),
        )
    )

    assert result.network_code == "toy"
    assert result.requested_mw == 0.5
    assert result.ranking_policy.startswith("verdict")
    assert len(result.rows) == 1
    assert result.rows[0].rank == 1
    assert result.top_rows == result.rows
    assert result.rows[0].bus_id == 1


def test_write_screening_outputs_creates_csv_and_markdown(tmp_path):
    result = screen_connections(ScreeningRequest(network_code="toy", requested_mw=0.5))

    outputs = write_screening_outputs(result, tmp_path)

    assert outputs.csv_path == tmp_path / "screening.csv"
    assert outputs.summary_path == tmp_path / "screening_summary.md"
    with outputs.csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["rank"] == "1"
    assert rows[0]["bus_id"] == "1"
    assert "firm_capacity_mw" in rows[0]
    assert "evaluated_conditional_mw" in rows[0]

    summary = outputs.summary_path.read_text(encoding="utf-8")
    assert "Top 10" in summary
    assert "best bus" in summary
    assert "Assumptions" in summary
    assert "Remaining Scientific Uncertainty" in summary


def test_render_screening_summary_reports_no_candidates():
    result = screen_connections(ScreeningRequest(network_code="toy", requested_mw=0.5))
    empty = type(result)(
        request=result.request,
        rows=(),
        top_rows=(),
        network_code=result.network_code,
        requested_mw=result.requested_mw,
        ranking_policy=result.ranking_policy,
    )

    rendered = render_screening_summary(empty)

    assert "No candidate bus passed the screening candidate policy" in rendered


def test_cli_screen_writes_csv_and_summary(tmp_path):
    exit_code = main(
        [
            "screen",
            "--network",
            "toy",
            "--requested-mw",
            "0.5",
            "--output",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "screening.csv").exists()
    assert (tmp_path / "screening_summary.md").exists()


def _row(
    *,
    bus_id: int,
    verdict: str,
    value: float,
    conditional: float,
    p90: float,
) -> ScreeningRow:
    return ScreeningRow(
        rank=0,
        bus_id=bus_id,
        bus_name=f"bus-{bus_id}",
        vn_kv=20.0,
        verdict=verdict,
        firm_injection_mw=1.0,
        firm_withdrawal_mw=1.0,
        firm_capacity_mw=1.0,
        conditional_capacity_mw=conditional,
        evaluated_conditional_mw=conditional,
        recommended_envelope="firm-only",
        expected_curtailment_hours=0,
        expected_curtailment_mwh=0.0,
        p50_curtailment_mw=0.0,
        p90_curtailment_mw=p90,
        ebitda_at_risk_eur=0.0,
        flexible_value_delta_eur=value,
        main_constraint="",
    )
