from __future__ import annotations

from thesegrid.models import ConnectionRequest, CurtailmentEstimate, EconomicComparison, Verdict


def estimate_economics(
    request: ConnectionRequest,
    curtailment: CurtailmentEstimate,
    annual_hours: int = 8760,
) -> EconomicComparison:
    gross_available_mwh = request.requested_mw * annual_hours
    served_energy_mwh = max(0.0, gross_available_mwh - curtailment.expected_mwh)
    connect_now_gross_margin = served_energy_mwh * request.economics.gross_margin_eur_per_mwh
    ebitda_at_risk = curtailment.expected_mwh * request.economics.curtailment_penalty_eur_per_mwh
    waiting_cost_avoided = (
        request.requested_mw
        * request.reinforcement_wait_years
        * request.economics.waiting_cost_eur_per_mw_year
    )
    return EconomicComparison(
        served_energy_mwh=round(served_energy_mwh, 6),
        connect_now_gross_margin_eur=round(connect_now_gross_margin, 2),
        ebitda_at_risk_eur=round(ebitda_at_risk, 2),
        waiting_cost_avoided_eur=round(waiting_cost_avoided, 2),
        flexible_value_delta_eur=round(waiting_cost_avoided - ebitda_at_risk, 2),
    )


def determine_verdict(
    requested_mw: float,
    firm_capacity_mw: float,
    conditional_capacity_mw: float,
    p90_curtailment_mw: float,
    p90_tolerance_mw: float,
    flexible_value_delta_eur: float,
) -> Verdict:
    if requested_mw <= firm_capacity_mw + 1e-9 and p90_curtailment_mw <= 1e-9:
        return "go"
    if (
        requested_mw <= conditional_capacity_mw + 1e-9
        and p90_curtailment_mw <= p90_tolerance_mw + 1e-9
        and flexible_value_delta_eur > 0
    ):
        return "go-with-conditions"
    return "no-go"
