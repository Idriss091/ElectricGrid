from __future__ import annotations

from dataclasses import replace

from thesegrid.capacity import estimate_firm_capacity
from thesegrid.conditional import recommend_envelope
from thesegrid.constraints import ConstraintSettings
from thesegrid.economics import determine_verdict, estimate_economics
from thesegrid.gabarits import annual_timestamps
from thesegrid.models import ConnectionRequest, CurtailmentEstimate, InvestmentMemo
from thesegrid.networks import load_network
from thesegrid.risk import estimate_curtailment


ASSUMPTIONS = (
    "AC steady-state power flow is evaluated with pandapower.",
    "BESS injection and withdrawal are assessed separately at the candidate bus.",
    "Voltage limits are 0.95-1.05 pu and thermal loading limit is 100% by default.",
    "RTE/CRE-inspired V1 gabarits are treated as ex-ante hourly seasonal calendars.",
    "Economic values are configurable proxies; eCO2mix price data is not assumed reusable "
    "for commercial pricing.",
)

SCIENTIFIC_UNCERTAINTY = (
    "SimBench benchmark networks are not a substitute for confidential French operator models.",
    "The MVP does not cover short-circuit, stability, protection, N-1, or dynamic studies.",
    "Single-bus assessment memos use simplified hourly curtailment logic unless the QSTS "
    "validation workflow is run separately.",
    "Commercial bankability still depends on the official grid-connection study.",
)


def assess_connection(
    request: ConnectionRequest,
    net: object | None = None,
    settings: ConstraintSettings | None = None,
    year: int = 2026,
) -> InvestmentMemo:
    settings = settings or ConstraintSettings()
    network = load_network(request.network_code) if net is None else net
    firm = estimate_firm_capacity(
        network,
        bus_id=request.bus_id,
        requested_mw=request.requested_mw,
        settings=settings,
    )
    timestamps = annual_timestamps(year)

    def is_economically_viable(mw: float, curtailment: CurtailmentEstimate) -> bool:
        candidate_request = replace(request, requested_mw=mw)
        return estimate_economics(candidate_request, curtailment).flexible_value_delta_eur > 0

    envelope = recommend_envelope(
        requested_mw=request.requested_mw,
        firm_injection_mw=firm.injection_mw,
        firm_withdrawal_mw=firm.withdrawal_mw,
        timestamps=timestamps,
        p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
        curtailment_tolerance_mwh=request.curtailment_tolerance_mwh_per_year,
        is_economically_viable=is_economically_viable,
    )
    curtailment = estimate_curtailment(envelope.curtailment_mw)
    economics = estimate_economics(request, curtailment)
    verdict = determine_verdict(
        requested_mw=request.requested_mw,
        firm_capacity_mw=firm.firm_capacity_mw,
        conditional_capacity_mw=envelope.conditional_capacity_mw,
        p90_curtailment_mw=curtailment.p90_mw,
        p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
        flexible_value_delta_eur=economics.flexible_value_delta_eur,
    )
    return InvestmentMemo(
        request=request,
        firm_injection_mw=round(firm.injection_mw, 6),
        firm_withdrawal_mw=round(firm.withdrawal_mw, 6),
        firm_capacity_mw=round(firm.firm_capacity_mw, 6),
        conditional_capacity_mw=round(envelope.conditional_capacity_mw, 6),
        evaluated_conditional_mw=round(envelope.evaluated_mw, 6),
        recommended_envelope=envelope.name,
        envelope_options=envelope.alternatives,
        curtailment=curtailment,
        economics=economics,
        binding_constraints=firm.binding_constraints,
        verdict=verdict,
        assumptions=ASSUMPTIONS,
        scientific_uncertainty=SCIENTIFIC_UNCERTAINTY,
    )
