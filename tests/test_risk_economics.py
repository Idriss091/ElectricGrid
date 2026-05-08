from thesegrid.economics import determine_verdict, estimate_economics
from thesegrid.models import ConnectionRequest, CurtailmentEstimate, EconomicAssumptions
from thesegrid.risk import estimate_curtailment


def test_estimate_curtailment_reports_hours_energy_and_percentiles():
    estimate = estimate_curtailment([0.0, 1.0, 2.0, 3.0], timestep_hours=1.0)

    assert estimate.expected_hours == 3
    assert estimate.expected_mwh == 6.0
    assert estimate.p50_mw == 1.5
    assert estimate.p90_mw == 2.7


def test_estimate_economics_turns_curtailment_into_ebitda_at_risk_and_wait_value():
    request = ConnectionRequest(
        network_code="toy",
        bus_id=1,
        requested_mw=2.0,
        reinforcement_wait_years=4.0,
        economics=EconomicAssumptions(
            gross_margin_eur_per_mwh=10.0,
            curtailment_penalty_eur_per_mwh=100.0,
            waiting_cost_eur_per_mw_year=50_000.0,
        ),
    )
    curtailment = CurtailmentEstimate(expected_hours=2, expected_mwh=3.0, p50_mw=1.0, p90_mw=2.0)

    economics = estimate_economics(request, curtailment)

    assert economics.ebitda_at_risk_eur == 300.0
    assert economics.waiting_cost_avoided_eur == 400_000.0
    assert economics.flexible_value_delta_eur == 399_700.0


def test_determine_verdict_distinguishes_go_conditions_and_no_go():
    assert (
        determine_verdict(
            requested_mw=5.0,
            firm_capacity_mw=5.0,
            conditional_capacity_mw=5.0,
            p90_curtailment_mw=0.0,
            p90_tolerance_mw=0.0,
            flexible_value_delta_eur=0.0,
        )
        == "go"
    )
    assert (
        determine_verdict(
            requested_mw=5.0,
            firm_capacity_mw=3.0,
            conditional_capacity_mw=5.0,
            p90_curtailment_mw=0.5,
            p90_tolerance_mw=1.0,
            flexible_value_delta_eur=10.0,
        )
        == "go-with-conditions"
    )
    assert (
        determine_verdict(
            requested_mw=5.0,
            firm_capacity_mw=3.0,
            conditional_capacity_mw=4.0,
            p90_curtailment_mw=0.5,
            p90_tolerance_mw=1.0,
            flexible_value_delta_eur=10.0,
        )
        == "no-go"
    )
