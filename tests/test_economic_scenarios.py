from thesegrid.economic_scenarios import (
    EconomicScenarioAssumptions,
    compare_economic_scenarios,
    render_economic_scenarios_markdown,
)


def test_compare_economic_scenarios_includes_wait_connect_now_and_resize():
    qsts_rows = [
        {
            "bus_id": "24",
            "requested_mw": "5.000000",
            "qsts_verdict": "no-go",
            "expected_curtailment_mwh": "21932.031457",
            "p90_curtailment_mw": "2.656250",
        }
    ]
    resize_rows = [
        {
            "scenario": "bus24_2mw",
            "requested_mw": "2.000000",
            "qsts_verdict": "go-with-conditions",
            "product_decision": "resize-recommended",
            "expected_curtailment_mwh": "19.812500",
            "p90_curtailment_mw": "0.000000",
        }
    ]
    assumptions = EconomicScenarioAssumptions(
        gross_revenue_eur_per_mw_year=100_000.0,
        capex_eur_per_kw=250.0,
        fixed_opex_eur_per_kw_year=10.0,
        curtailment_penalty_eur_per_mwh=100.0,
        discount_rate=0.08,
        analysis_years=5.0,
    )

    scenarios = compare_economic_scenarios(qsts_rows, resize_rows, assumptions)

    assert [scenario.name for scenario in scenarios] == [
        "wait_for_reinforcement",
        "connect_now_5mw",
        "resize_bus24_2mw",
    ]
    wait, connect, resize = scenarios
    assert wait.mw == 5.0
    assert wait.verdict == "wait"
    assert wait.capex_eur == 0.0
    assert connect.annual_curtailment_loss_eur == 2_193_203.15
    assert connect.annual_ebitda_proxy_eur < 0
    assert resize.mw == 2.0
    assert resize.verdict == "go-with-conditions"
    assert resize.annual_curtailment_loss_eur == 1_981.25
    assert resize.proxy_npv_eur < wait.proxy_npv_eur


def test_render_economic_scenarios_markdown_labels_proxy_assumptions():
    scenarios = compare_economic_scenarios(
        qsts_rows=[
            {
                "bus_id": "24",
                "requested_mw": "5.000000",
                "qsts_verdict": "no-go",
                "expected_curtailment_mwh": "21932.031457",
                "p90_curtailment_mw": "2.656250",
            }
        ],
        resize_rows=[],
        assumptions=EconomicScenarioAssumptions(),
    )

    markdown = render_economic_scenarios_markdown(scenarios, EconomicScenarioAssumptions())

    assert "Proxy Economic Scenarios" in markdown
    assert "not bankable revenue modelling" in markdown
    assert "gross_revenue_eur_per_mw_year" in markdown
    assert "connect_now_5mw" in markdown
