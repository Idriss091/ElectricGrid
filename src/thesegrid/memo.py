from __future__ import annotations

from pathlib import Path

from thesegrid.models import InvestmentMemo


def render_investment_memo(memo: InvestmentMemo) -> str:
    request = memo.request
    constraints = (
        "\n".join(f"- {violation.description}" for violation in memo.binding_constraints)
        if memo.binding_constraints
        else "- None at requested capacity."
    )
    assumptions = "\n".join(f"- {assumption}" for assumption in memo.assumptions)
    uncertainty = "\n".join(f"- {item}" for item in memo.scientific_uncertainty)
    envelope_options = _render_envelope_options(memo)
    return f"""# Flexible Connection Pre-Feasibility Memo

This memo is an early-stage buyer-side decision aid. It does not replace an official grid-connection study.

Cette enveloppe est une approximation pré-faisabilité inspirée du cadre RTE/CRE ; elle ne constitue pas une PTF ni une offre officielle RTE/Enedis.

## Request

- network_code: {request.network_code}
- bus_id: {request.bus_id}
- asset: {request.asset}
- requested_mw: {request.requested_mw:.3f}
- reinforcement_wait_years: {request.reinforcement_wait_years:.2f}

## Verdict

- recommendation: {memo.verdict}
- recommended_envelope: {memo.recommended_envelope}

## Capacity

- firm_injection_mw: {memo.firm_injection_mw:.3f}
- firm_withdrawal_mw: {memo.firm_withdrawal_mw:.3f}
- firm_capacity_mw: {memo.firm_capacity_mw:.3f}
- conditional_capacity_mw: {memo.conditional_capacity_mw:.3f}
- evaluated_conditional_mw: {memo.evaluated_conditional_mw:.3f}

## Envelope Comparison

{envelope_options}

## Curtailment Risk

- expected_curtailment_hours: {memo.curtailment.expected_hours}
- expected_curtailment_mwh: {memo.curtailment.expected_mwh:.3f}
- p50_curtailment_mw: {memo.curtailment.p50_mw:.3f}
- p90_curtailment_mw: {memo.curtailment.p90_mw:.3f}

## Economics

- served_energy_mwh: {memo.economics.served_energy_mwh:.3f}
- connect_now_gross_margin_eur: {memo.economics.connect_now_gross_margin_eur:.2f}
- ebitda_at_risk_eur: {memo.economics.ebitda_at_risk_eur:.2f}
- waiting_cost_avoided_eur: {memo.economics.waiting_cost_avoided_eur:.2f}
- flexible_value_delta_eur: {memo.economics.flexible_value_delta_eur:.2f}

## Binding Constraints

{constraints}

## Assumptions

{assumptions}

## Remaining Scientific Uncertainty

{uncertainty}
"""


def write_investment_memo(memo: InvestmentMemo, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_investment_memo(memo), encoding="utf-8")
    return output_path


def _render_envelope_options(memo: InvestmentMemo) -> str:
    if not memo.envelope_options:
        return "No envelope alternatives evaluated."
    lines = [
        "| envelope | evaluated_mw | hours | mwh | p50_mw | p90_mw |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for option in memo.envelope_options:
        marker = " (recommended)" if option.name == memo.recommended_envelope else ""
        lines.append(
            "| "
            f"{option.name}{marker} | {option.evaluated_mw:.3f} | "
            f"{option.expected_curtailment_hours} | "
            f"{option.expected_curtailment_mwh:.3f} | "
            f"{option.p50_curtailment_mw:.3f} | "
            f"{option.p90_curtailment_mw:.3f} |"
        )
    return "\n".join(lines)
