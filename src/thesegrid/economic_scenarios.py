from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EconomicScenarioAssumptions:
    gross_revenue_eur_per_mw_year: float = 100_000.0
    capex_eur_per_kw: float = 250.0
    fixed_opex_eur_per_kw_year: float = 10.0
    curtailment_penalty_eur_per_mwh: float = 100.0
    discount_rate: float = 0.08
    analysis_years: float = 5.0


@dataclass(frozen=True)
class EconomicScenario:
    name: str
    mw: float
    verdict: str
    expected_curtailment_mwh: float
    p90_curtailment_mw: float
    annual_gross_revenue_eur: float
    annual_curtailment_loss_eur: float
    annual_fixed_opex_eur: float
    capex_eur: float
    annual_ebitda_proxy_eur: float
    proxy_npv_eur: float


def compare_economic_scenarios(
    qsts_rows: list[dict[str, str]],
    resize_rows: list[dict[str, str]],
    assumptions: EconomicScenarioAssumptions,
) -> tuple[EconomicScenario, ...]:
    if not qsts_rows:
        return ()
    requested_mw = max(_float(row.get("requested_mw")) for row in qsts_rows)
    scenarios = [
        _scenario(
            name="wait_for_reinforcement",
            mw=requested_mw,
            verdict="wait",
            expected_curtailment_mwh=0.0,
            p90_curtailment_mw=0.0,
            assumptions=assumptions,
            include_capex=False,
        )
    ]
    worst_connect_row = max(
        qsts_rows,
        key=lambda row: _float(row.get("expected_curtailment_mwh")),
    )
    scenarios.append(
        _scenario(
            name=f"connect_now_{_mw_slug(requested_mw)}",
            mw=requested_mw,
            verdict=worst_connect_row.get("qsts_verdict", ""),
            expected_curtailment_mwh=_float(worst_connect_row.get("expected_curtailment_mwh")),
            p90_curtailment_mw=_float(worst_connect_row.get("p90_curtailment_mw")),
            assumptions=assumptions,
            include_capex=True,
        )
    )
    for row in resize_rows:
        if row.get("product_decision") != "resize-recommended":
            continue
        mw = _float(row.get("requested_mw"))
        scenarios.append(
            _scenario(
                name=f"resize_{row.get('scenario', _mw_slug(mw))}",
                mw=mw,
                verdict=row.get("qsts_verdict", ""),
                expected_curtailment_mwh=_float(row.get("expected_curtailment_mwh")),
                p90_curtailment_mw=_float(row.get("p90_curtailment_mw")),
                assumptions=assumptions,
                include_capex=True,
            )
        )
    return tuple(scenarios)


def economic_scenario_rows(scenarios: tuple[EconomicScenario, ...]) -> list[dict[str, object]]:
    return [asdict(scenario) for scenario in scenarios]


def render_economic_scenarios_markdown(
    scenarios: tuple[EconomicScenario, ...],
    assumptions: EconomicScenarioAssumptions,
) -> str:
    return f"""# Proxy Economic Scenarios

This comparison is proxy economics, not bankable revenue modelling. It is intended to
compare wait, connect-now, and resize decisions under explicit assumptions.

## Assumptions

- gross_revenue_eur_per_mw_year: {assumptions.gross_revenue_eur_per_mw_year:.2f}
- capex_eur_per_kw: {assumptions.capex_eur_per_kw:.2f}
- fixed_opex_eur_per_kw_year: {assumptions.fixed_opex_eur_per_kw_year:.2f}
- curtailment_penalty_eur_per_mwh: {assumptions.curtailment_penalty_eur_per_mwh:.2f}
- discount_rate: {assumptions.discount_rate:.4f}
- analysis_years: {assumptions.analysis_years:.2f}

## Scenarios

{_scenario_table(scenarios)}
"""


def _scenario(
    name: str,
    mw: float,
    verdict: str,
    expected_curtailment_mwh: float,
    p90_curtailment_mw: float,
    assumptions: EconomicScenarioAssumptions,
    include_capex: bool,
) -> EconomicScenario:
    annual_gross_revenue = mw * assumptions.gross_revenue_eur_per_mw_year
    annual_curtailment_loss = expected_curtailment_mwh * assumptions.curtailment_penalty_eur_per_mwh
    annual_fixed_opex = mw * 1000.0 * assumptions.fixed_opex_eur_per_kw_year
    capex = mw * 1000.0 * assumptions.capex_eur_per_kw if include_capex else 0.0
    annual_ebitda = annual_gross_revenue - annual_curtailment_loss - annual_fixed_opex
    proxy_npv = _discounted_annuity(
        annual_ebitda,
        years=assumptions.analysis_years,
        discount_rate=assumptions.discount_rate,
    ) - capex
    return EconomicScenario(
        name=name,
        mw=round(mw, 6),
        verdict=verdict,
        expected_curtailment_mwh=round(expected_curtailment_mwh, 6),
        p90_curtailment_mw=round(p90_curtailment_mw, 6),
        annual_gross_revenue_eur=round(annual_gross_revenue, 2),
        annual_curtailment_loss_eur=round(annual_curtailment_loss, 2),
        annual_fixed_opex_eur=round(annual_fixed_opex, 2),
        capex_eur=round(capex, 2),
        annual_ebitda_proxy_eur=round(annual_ebitda, 2),
        proxy_npv_eur=round(proxy_npv, 2),
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


def _scenario_table(scenarios: tuple[EconomicScenario, ...]) -> str:
    if not scenarios:
        return "No economic scenarios available."
    lines = [
        "| scenario | MW | verdict | curtailed MWh | p90 MW | gross revenue | curtailment loss | fixed OPEX | CAPEX | proxy NPV |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario in scenarios:
        lines.append(
            "| "
            f"{scenario.name} | {scenario.mw:.3f} | {scenario.verdict} | "
            f"{scenario.expected_curtailment_mwh:.3f} | {scenario.p90_curtailment_mw:.3f} | "
            f"{scenario.annual_gross_revenue_eur:.2f} | "
            f"{scenario.annual_curtailment_loss_eur:.2f} | "
            f"{scenario.annual_fixed_opex_eur:.2f} | {scenario.capex_eur:.2f} | "
            f"{scenario.proxy_npv_eur:.2f} |"
        )
    return "\n".join(lines)


def _float(value: str | None) -> float:
    if value in {None, ""}:
        return 0.0
    return float(value)


def _mw_slug(value: float) -> str:
    return f"{value:.0f}mw" if value.is_integer() else f"{value:.3f}mw".replace(".", "p")
