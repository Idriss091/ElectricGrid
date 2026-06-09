from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QstsEconomicsProxy:
    storage_duration_hours: float
    reinforcement_wait_years: float
    discount_rate: float
    energy_capacity_mwh: float
    capex_eur: float
    annual_gross_revenue_eur: float
    annual_curtailment_loss_eur: float
    annual_fixed_opex_eur: float
    annual_ebitda_proxy_eur: float
    connect_now_value_eur: float
    wait_value_eur: float
    delta_npv_eur: float


def qsts_economics_proxy(result: Any) -> QstsEconomicsProxy:
    bus = result.buses[0] if result.buses else None
    return qsts_bus_economics_proxy(result.request, bus)


def qsts_bus_economics_proxy(
    request: Any,
    bus: Any | None,
) -> QstsEconomicsProxy:
    curtailed_mwh = bus.weighted_curtailment_mwh if bus is not None else 0.0
    requested_kw = request.requested_mw * 1000.0
    energy_capacity_mwh = request.requested_mw * request.storage_duration_hours
    capex = requested_kw * request.capex_eur_per_kw
    annual_gross_revenue = request.requested_mw * request.gross_revenue_eur_per_mw_year
    annual_curtailment_loss = curtailed_mwh * request.curtailment_penalty_eur_per_mwh
    annual_fixed_opex = requested_kw * request.fixed_opex_eur_per_kw_year
    annual_ebitda = annual_gross_revenue - annual_curtailment_loss - annual_fixed_opex
    connect_now_value = _discounted_annuity(
        annual_ebitda,
        years=request.reinforcement_wait_years,
        discount_rate=request.discount_rate,
    )
    wait_value = _discounted_annuity(
        annual_gross_revenue - annual_fixed_opex,
        years=request.reinforcement_wait_years,
        discount_rate=request.discount_rate,
    )
    return QstsEconomicsProxy(
        storage_duration_hours=round(request.storage_duration_hours, 6),
        reinforcement_wait_years=round(request.reinforcement_wait_years, 6),
        discount_rate=round(request.discount_rate, 6),
        energy_capacity_mwh=round(energy_capacity_mwh, 6),
        capex_eur=round(capex, 6),
        annual_gross_revenue_eur=round(annual_gross_revenue, 6),
        annual_curtailment_loss_eur=round(annual_curtailment_loss, 6),
        annual_fixed_opex_eur=round(annual_fixed_opex, 6),
        annual_ebitda_proxy_eur=round(annual_ebitda, 6),
        connect_now_value_eur=round(connect_now_value - capex, 6),
        wait_value_eur=round(wait_value, 6),
        delta_npv_eur=round((connect_now_value - capex) - wait_value, 6),
    )


def _discounted_annuity(value: float, years: float, discount_rate: float) -> float:
    if years <= 0:
        return 0.0
    whole_years = int(years)
    fractional_year = years - whole_years
    total = 0.0
    for year in range(1, whole_years + 1):
        total += value / ((1.0 + discount_rate) ** year)
    if fractional_year > 0:
        total += (value * fractional_year) / ((1.0 + discount_rate) ** (whole_years + 1))
    return total
