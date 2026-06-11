from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from thesegrid.decision_frontier import decision_frontier_rows
from thesegrid.qsts_decisions import (
    decision_confidence,
    qsts_verdict_driver,
    recommended_next_action,
    validation_level,
)
from thesegrid.qsts_economics import qsts_bus_economics_proxy


QSTS_RESULT_COLUMNS = (
    "rank",
    "bus_id",
    "bus_name",
    "product_decision",
    "selected_policy",
    "qsts_verdict",
    "validation_level",
    "decision_confidence",
    "recommended_next_action",
    "requested_mw",
    "static_firm_capacity_mw",
    "static_conditional_capacity_mw",
    "baseline_mode",
    "p90_curtailment_tolerance_mw",
    "feasible_hours",
    "violation_hours",
    "expected_curtailment_mwh",
    "sampled_curtailment_mwh",
    "weighted_curtailment_mwh",
    "curtailment_energy_ratio",
    "p50_curtailment_mw",
    "p90_curtailment_mw",
    "main_recurring_constraint",
)

QSTS_DETAIL_COLUMNS = (
    "timestamp",
    "direction",
    "requested_mw",
    "feasible_mw",
    "curtailed_mw",
    "converged",
    "min_vm_pu",
    "max_vm_pu",
    "max_loading_percent",
    "binding_constraint",
    "incremental_binding_constraint",
)

QSTS_ENVELOPE_COLUMNS = (
    "timestamp",
    "bus_id",
    "bus_name",
    "direction",
    "requested_mw",
    "allowed_mw",
    "curtailed_mw",
    "incremental_binding_constraint",
    "qsts_verdict_context",
)

QSTS_ENVELOPE_SUMMARY_COLUMNS = (
    "bus_id",
    "bus_name",
    "month",
    "hour",
    "direction",
    "allowed_mw_p50",
    "allowed_mw_p90",
    "allowed_mw_min",
    "curtailed_mw_p50",
    "curtailed_mw_p90",
    "dominant_incremental_constraint",
)

INVESTOR_DECISION_COLUMNS = (
    "rank",
    "bus_id",
    "bus_name",
    "product_decision",
    "selected_policy",
    "qsts_verdict",
    "validation_level",
    "decision_confidence",
    "recommended_next_action",
    "static_firm_capacity_mw",
    "static_conditional_capacity_mw",
    "qsts_p90_curtailment_mw",
    "qsts_expected_curtailment_mwh",
    "sampled_curtailment_mwh",
    "weighted_curtailment_mwh",
    "curtailment_energy_ratio",
    "main_recurring_constraint",
)

QSTS_ECONOMICS_COLUMNS = (
    "bus_id",
    "bus_name",
    "qsts_verdict",
    "requested_mw",
    "storage_duration_hours",
    "energy_capacity_mwh",
    "capex_eur",
    "annual_gross_revenue_eur",
    "annual_curtailment_loss_eur",
    "annual_fixed_opex_eur",
    "annual_ebitda_proxy_eur",
    "connect_now_value_eur",
    "wait_value_eur",
    "delta_npv_eur",
)

CONTRACTUAL_ENVELOPE_COLUMNS = (
    "bus_id",
    "bus_name",
    "direction",
    "season",
    "time_block",
    "allowed_mw_p10",
    "allowed_mw_p25",
    "allowed_mw_p50",
    "allowed_mw_min",
    "curtailed_mw_p90",
    "dominant_incremental_constraint",
)

STATIC_VS_QSTS_COMPARISON_COLUMNS = (
    "bus_id",
    "bus_name",
    "qsts_verdict",
    "static_firm_capacity_mw",
    "static_conditional_capacity_mw",
    "contractual_allowed_mw_p10_min",
    "contractual_allowed_mw_p25_min",
    "contractual_allowed_mw_p50_min",
    "contractual_allowed_mw_min",
    "qsts_p90_curtailment_mw",
    "qsts_expected_curtailment_mwh",
    "main_recurring_constraint",
    "runtime_seconds",
)

QSTS_RISK_SUMMARY_COLUMNS = (
    "bus_id",
    "bus_name",
    "qsts_verdict",
    "curtailment_hours",
    "expected_curtailment_mwh",
    "sampled_curtailment_mwh",
    "weighted_curtailment_mwh",
    "curtailment_energy_ratio",
    "curtailment_p90_mw",
    "curtailment_p95_mw",
    "curtailment_p99_mw",
    "curtailment_max_mw",
    "max_event_hours",
    "max_event_mwh",
    "dominant_constraint",
    "verdict_driver",
    "tail_risk_flag",
)


def envelope_record_row(record: Any) -> dict[str, object]:
    return {
        "timestamp": record.timestamp,
        "bus_id": record.bus_id,
        "bus_name": record.bus_name,
        "direction": record.direction,
        "requested_mw": f"{record.requested_mw:.6f}",
        "allowed_mw": f"{record.allowed_mw:.6f}",
        "curtailed_mw": f"{record.curtailed_mw:.6f}",
        "incremental_binding_constraint": record.incremental_binding_constraint,
        "qsts_verdict_context": record.qsts_verdict_context,
    }


def envelope_summary_row(row: Any) -> dict[str, object]:
    return {
        "bus_id": row.bus_id,
        "bus_name": row.bus_name,
        "month": row.month,
        "hour": row.hour,
        "direction": row.direction,
        "allowed_mw_p50": f"{row.allowed_mw_p50:.6f}",
        "allowed_mw_p90": f"{row.allowed_mw_p90:.6f}",
        "allowed_mw_min": f"{row.allowed_mw_min:.6f}",
        "curtailed_mw_p50": f"{row.curtailed_mw_p50:.6f}",
        "curtailed_mw_p90": f"{row.curtailed_mw_p90:.6f}",
        "dominant_incremental_constraint": row.dominant_incremental_constraint,
    }


def contractual_envelope_row(row: Any) -> dict[str, object]:
    return {
        "bus_id": row.bus_id,
        "bus_name": row.bus_name,
        "direction": row.direction,
        "season": row.season,
        "time_block": row.time_block,
        "allowed_mw_p10": f"{row.allowed_mw_p10:.6f}",
        "allowed_mw_p25": f"{row.allowed_mw_p25:.6f}",
        "allowed_mw_p50": f"{row.allowed_mw_p50:.6f}",
        "allowed_mw_min": f"{row.allowed_mw_min:.6f}",
        "curtailed_mw_p90": f"{row.curtailed_mw_p90:.6f}",
        "dominant_incremental_constraint": row.dominant_incremental_constraint,
    }


def risk_summary_row(row: Any) -> dict[str, object]:
    return {
        "bus_id": row.bus_id,
        "bus_name": row.bus_name,
        "qsts_verdict": row.qsts_verdict,
        "curtailment_hours": row.curtailment_hours,
        "expected_curtailment_mwh": f"{row.expected_curtailment_mwh:.6f}",
        "sampled_curtailment_mwh": f"{row.sampled_curtailment_mwh:.6f}",
        "weighted_curtailment_mwh": f"{row.weighted_curtailment_mwh:.6f}",
        "curtailment_energy_ratio": f"{row.curtailment_energy_ratio:.6f}",
        "curtailment_p90_mw": f"{row.curtailment_p90_mw:.6f}",
        "curtailment_p95_mw": f"{row.curtailment_p95_mw:.6f}",
        "curtailment_p99_mw": f"{row.curtailment_p99_mw:.6f}",
        "curtailment_max_mw": f"{row.curtailment_max_mw:.6f}",
        "max_event_hours": row.max_event_hours,
        "max_event_mwh": f"{row.max_event_mwh:.6f}",
        "dominant_constraint": row.dominant_constraint,
        "verdict_driver": row.verdict_driver,
        "tail_risk_flag": row.tail_risk_flag,
    }


def qsts_economics_row(request: Any, bus: Any) -> dict[str, object]:
    economics = qsts_bus_economics_proxy(request, bus)
    return {
        "bus_id": bus.bus_id,
        "bus_name": bus.bus_name,
        "qsts_verdict": bus.qsts_verdict,
        "requested_mw": f"{bus.requested_mw:.6f}",
        "storage_duration_hours": f"{economics.storage_duration_hours:.6f}",
        "energy_capacity_mwh": f"{economics.energy_capacity_mwh:.6f}",
        "capex_eur": f"{economics.capex_eur:.6f}",
        "annual_gross_revenue_eur": f"{economics.annual_gross_revenue_eur:.6f}",
        "annual_curtailment_loss_eur": f"{economics.annual_curtailment_loss_eur:.6f}",
        "annual_fixed_opex_eur": f"{economics.annual_fixed_opex_eur:.6f}",
        "annual_ebitda_proxy_eur": f"{economics.annual_ebitda_proxy_eur:.6f}",
        "connect_now_value_eur": f"{economics.connect_now_value_eur:.6f}",
        "wait_value_eur": f"{economics.wait_value_eur:.6f}",
        "delta_npv_eur": f"{economics.delta_npv_eur:.6f}",
    }


def decision_frontier_row(row: Any) -> dict[str, object]:
    return {
        "bus_id": row.bus_id,
        "bus_name": row.bus_name,
        "policy": row.policy,
        "qsts_p90_mw": f"{row.qsts_p90_mw:.6f}",
        "p90_curtailment_ratio": f"{row.p90_curtailment_ratio:.6f}",
        "weighted_curtailment_mwh": f"{row.weighted_curtailment_mwh:.6f}",
        "curtailment_energy_ratio": f"{row.curtailment_energy_ratio:.6f}",
        "max_event_hours": row.max_event_hours,
        "max_event_mwh": f"{row.max_event_mwh:.6f}",
        "max_event_mwh_per_mw": f"{row.max_event_mwh_per_mw:.6f}",
        "policy_max_p90_ratio": f"{row.policy_definition.max_p90_ratio:.6f}",
        "policy_max_energy_ratio": f"{row.policy_definition.max_energy_ratio:.6f}",
        "policy_max_event_hours": row.policy_definition.max_event_hours,
        "policy_max_event_mwh_per_mw": f"{row.policy_definition.max_event_mwh_per_mw:.6f}",
        "policy_conditional_max_event_mwh_per_mw": (
            ""
            if row.policy_definition.conditional_max_event_mwh_per_mw is None
            else f"{row.policy_definition.conditional_max_event_mwh_per_mw:.6f}"
        ),
        "frontier_verdict": row.frontier_verdict,
        "validation_level": row.validation_level,
    }


def bus_result_row(
    bus: Any,
    request: Any,
    evaluated_time_steps: int = 0,
) -> dict[str, object]:
    policy_verdict = selected_policy_verdict(bus, request, evaluated_time_steps)
    driver = qsts_verdict_driver(
        bus.curtailment,
        p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
        mwh_tolerance=request.expected_curtailment_tolerance_mwh,
    )
    return {
        "rank": bus.rank,
        "bus_id": bus.bus_id,
        "bus_name": bus.bus_name,
        "product_decision": policy_verdict,
        "selected_policy": request.selected_policy,
        "qsts_verdict": policy_verdict,
        "validation_level": validation_level(request, evaluated_time_steps),
        "decision_confidence": decision_confidence(request, evaluated_time_steps),
        "recommended_next_action": recommended_next_action(
            policy_verdict,
            driver,
            request,
            evaluated_time_steps,
        ),
        "requested_mw": f"{bus.requested_mw:.6f}",
        "static_firm_capacity_mw": f"{bus.static_firm_capacity_mw:.6f}",
        "static_conditional_capacity_mw": f"{bus.static_conditional_capacity_mw:.6f}",
        "baseline_mode": "incremental",
        "p90_curtailment_tolerance_mw": f"{bus.p90_curtailment_tolerance_mw:.6f}",
        "feasible_hours": bus.feasible_hours,
        "violation_hours": bus.violation_hours,
        "expected_curtailment_mwh": f"{bus.curtailment.expected_mwh:.6f}",
        "sampled_curtailment_mwh": f"{bus.sampled_curtailment_mwh:.6f}",
        "weighted_curtailment_mwh": f"{bus.weighted_curtailment_mwh:.6f}",
        "curtailment_energy_ratio": f"{bus.curtailment_energy_ratio:.6f}",
        "p50_curtailment_mw": f"{bus.curtailment.p50_mw:.6f}",
        "p90_curtailment_mw": f"{bus.curtailment.p90_mw:.6f}",
        "main_recurring_constraint": bus.main_recurring_constraint,
    }


def investor_decision_row(
    bus: Any,
    request: Any,
    evaluated_time_steps: int = 0,
) -> dict[str, object]:
    policy_verdict = selected_policy_verdict(bus, request, evaluated_time_steps)
    driver = qsts_verdict_driver(
        bus.curtailment,
        p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
        mwh_tolerance=request.expected_curtailment_tolerance_mwh,
    )
    return {
        "rank": bus.rank,
        "bus_id": bus.bus_id,
        "bus_name": bus.bus_name,
        "product_decision": policy_verdict,
        "selected_policy": request.selected_policy,
        "qsts_verdict": policy_verdict,
        "validation_level": validation_level(request, evaluated_time_steps),
        "decision_confidence": decision_confidence(request, evaluated_time_steps),
        "recommended_next_action": recommended_next_action(
            policy_verdict,
            driver,
            request,
            evaluated_time_steps,
        ),
        "static_firm_capacity_mw": f"{bus.static_firm_capacity_mw:.6f}",
        "static_conditional_capacity_mw": f"{bus.static_conditional_capacity_mw:.6f}",
        "qsts_p90_curtailment_mw": f"{bus.curtailment.p90_mw:.6f}",
        "qsts_expected_curtailment_mwh": f"{bus.curtailment.expected_mwh:.6f}",
        "sampled_curtailment_mwh": f"{bus.sampled_curtailment_mwh:.6f}",
        "weighted_curtailment_mwh": f"{bus.weighted_curtailment_mwh:.6f}",
        "curtailment_energy_ratio": f"{bus.curtailment_energy_ratio:.6f}",
        "main_recurring_constraint": bus.main_recurring_constraint,
    }


def render_qsts_table(
    buses: tuple[Any, ...],
    request: Any,
    evaluated_time_steps: int = 0,
) -> str:
    lines = [
        "| rank | bus_id | bus_name | product_decision | selected_policy | validation_level | confidence | next_action | static_firm_mw | static_conditional_mw | qsts_p90_mw | qsts_mwh |",
        "| ---: | ---: | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for bus in buses:
        policy_verdict = selected_policy_verdict(bus, request, evaluated_time_steps)
        driver = qsts_verdict_driver(
            bus.curtailment,
            p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
            mwh_tolerance=request.expected_curtailment_tolerance_mwh,
        )
        lines.append(
            "| "
            f"{bus.rank} | {bus.bus_id} | {bus.bus_name} | {policy_verdict} | "
            f"{request.selected_policy} | "
            f"{validation_level(request, evaluated_time_steps)} | "
            f"{decision_confidence(request, evaluated_time_steps)} | "
            f"{recommended_next_action(policy_verdict, driver, request, evaluated_time_steps)} | "
            f"{bus.static_firm_capacity_mw:.3f} | {bus.static_conditional_capacity_mw:.3f} | "
            f"{bus.curtailment.p90_mw:.3f} | {bus.curtailment.expected_mwh:.3f} |"
        )
    return "\n".join(lines)


def render_baseline_table(buses: tuple[Any, ...]) -> str:
    lines = [
        "| bus_id | baseline_violating_hours | dominant_pre_existing_constraint | max_voltage_pu | max_loading_percent |",
        "| ---: | ---: | --- | ---: | ---: |",
    ]
    for bus in buses:
        lines.append(
            "| "
            f"{bus.bus_id} | {bus.baseline_violating_hours} | "
            f"{bus.baseline_main_constraint or '-'} | "
            f"{format_optional_float(bus.baseline_max_vm_pu)} | "
            f"{format_optional_float(bus.baseline_max_loading_percent)} |"
        )
    return "\n".join(lines)


def render_investor_decision_table(
    buses: tuple[Any, ...],
    request: Any,
    evaluated_time_steps: int = 0,
) -> str:
    lines = [
        "| rank | bus_id | product_decision | selected_policy | validation_level | confidence | next_action | static_firm_mw | static_conditional_mw | qsts_p90_mw | qsts_mwh | main_constraint |",
        "| ---: | ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for bus in buses:
        policy_verdict = selected_policy_verdict(bus, request, evaluated_time_steps)
        driver = qsts_verdict_driver(
            bus.curtailment,
            p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
            mwh_tolerance=request.expected_curtailment_tolerance_mwh,
        )
        lines.append(
            "| "
            f"{bus.rank} | {bus.bus_id} | {policy_verdict} | {request.selected_policy} | "
            f"{validation_level(request, evaluated_time_steps)} | "
            f"{decision_confidence(request, evaluated_time_steps)} | "
            f"{recommended_next_action(policy_verdict, driver, request, evaluated_time_steps)} | "
            f"{bus.static_firm_capacity_mw:.3f} | "
            f"{bus.static_conditional_capacity_mw:.3f} | "
            f"{bus.curtailment.p90_mw:.3f} | "
            f"{bus.curtailment.expected_mwh:.3f} | "
            f"{bus.main_recurring_constraint or '-'} |"
        )
    return "\n".join(lines)


def render_risk_summary_table(rows: tuple[Any, ...]) -> str:
    if not rows:
        return "No QSTS risk rows available."
    lines = [
        "| bus_id | verdict | driver | tail_risk | hours | mwh | p90_mw | p95_mw | p99_mw | max_mw | max_event_h | max_event_mwh | dominant_constraint |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row.bus_id} | {row.qsts_verdict} | {row.verdict_driver} | "
            f"{row.tail_risk_flag} | {row.curtailment_hours} | "
            f"{row.expected_curtailment_mwh:.3f} | {row.curtailment_p90_mw:.3f} | "
            f"{row.curtailment_p95_mw:.3f} | {row.curtailment_p99_mw:.3f} | "
            f"{row.curtailment_max_mw:.3f} | {row.max_event_hours} | "
            f"{row.max_event_mwh:.3f} | {row.dominant_constraint or '-'} |"
        )
    return "\n".join(lines)


def render_decision_drivers(rows: tuple[Any, ...]) -> str:
    if not rows:
        return "No QSTS decision drivers available."
    lines = [
        "| bus_id | verdict | driver | interpretation |",
        "| ---: | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row.bus_id} | {row.qsts_verdict} | {row.verdict_driver} | "
            f"{driver_interpretation(row.verdict_driver, row.tail_risk_flag)} |"
        )
    return "\n".join(lines)


def render_decision_snapshot(
    result: Any,
    risk_rows: tuple[Any, ...],
) -> str:
    if not result.buses:
        return "No QSTS decision rows available."
    primary_bus = result.buses[0]
    primary_risk = risk_rows[0]
    primary_decision = selected_policy_verdict(
        primary_bus,
        result.request,
        result.performance.evaluated_time_steps,
    )
    lines = [
        f"- validation_level: {validation_level(result.request, result.performance.evaluated_time_steps)}",
        f"- decision_confidence: {decision_confidence(result.request, result.performance.evaluated_time_steps)}",
        f"- selected_policy: {result.request.selected_policy}",
        f"- product_decision: {primary_decision}",
        "- investor_reference: qsts_full_year",
        "- recommended_next_action: "
        f"{recommended_next_action(primary_decision, primary_risk.verdict_driver, result.request, result.performance.evaluated_time_steps)}",
        "",
        "| bus_id | product_decision | selected_policy | p90_mw | expected_mwh | p95_mw | p99_mw | max_mw | dominant_constraint | recommended_next_action |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    risk_by_bus = {row.bus_id: row for row in risk_rows}
    for bus in result.buses:
        risk = risk_by_bus[bus.bus_id]
        product_decision = selected_policy_verdict(
            bus,
            result.request,
            result.performance.evaluated_time_steps,
        )
        lines.append(
            "| "
            f"{bus.bus_id} | {product_decision} | {result.request.selected_policy} | "
            f"{bus.curtailment.p90_mw:.3f} | {bus.curtailment.expected_mwh:.3f} | "
            f"{risk.curtailment_p95_mw:.3f} | {risk.curtailment_p99_mw:.3f} | "
            f"{risk.curtailment_max_mw:.3f} | {risk.dominant_constraint or '-'} | "
            f"{recommended_next_action(product_decision, risk.verdict_driver, result.request, result.performance.evaluated_time_steps)} |"
        )
    return "\n".join(lines)


def driver_interpretation(verdict_driver: str, tail_risk_flag: bool) -> str:
    if verdict_driver == "no_curtailment":
        return "No QSTS curtailment was observed."
    if tail_risk_flag:
        return "P90 can look acceptable while MWh shows risk rare but energetically material."
    if verdict_driver == "p90_exceeds_tolerance":
        return "Hourly curtailment magnitude exceeds the configured P90 tolerance."
    if verdict_driver == "both_exceed":
        return "Both hourly magnitude and expected energy exceed configured tolerances."
    if verdict_driver == "mwh_exceeds_tolerance":
        return "Expected curtailed energy exceeds the configured MWh tolerance."
    return "Curtailment remains within the configured conditional tolerance."


def render_qsts_investment_table(
    result: Any,
    contractual_rows: tuple[Any, ...],
) -> str:
    contract_ranges = contractual_p10_ranges(contractual_rows)
    lines = [
        "| rank | bus_id | product_decision | selected_policy | firm_mw | conditional_mw | contract_p10_min_mw | contract_p10_max_mw | qsts_p90_mw | qsts_mwh | dominant_constraint |",
        "| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for bus in result.buses:
        contract_min, contract_max = contract_ranges.get(bus.bus_id, (None, None))
        product_decision = selected_policy_verdict(
            bus,
            result.request,
            result.performance.evaluated_time_steps,
        )
        lines.append(
            "| "
            f"{bus.rank} | {bus.bus_id} | {product_decision} | {result.request.selected_policy} | "
            f"{bus.static_firm_capacity_mw:.3f} | "
            f"{bus.static_conditional_capacity_mw:.3f} | "
            f"{format_optional_float(contract_min)} | "
            f"{format_optional_float(contract_max)} | "
            f"{bus.curtailment.p90_mw:.3f} | "
            f"{bus.curtailment.expected_mwh:.3f} | "
            f"{bus.main_recurring_constraint or '-'} |"
        )
    return "\n".join(lines)


def render_qsts_economics_table(result: Any) -> str:
    if not result.buses:
        return "No per-bus economics rows available."
    lines = [
        "| bus_id | product_decision | selected_policy | weighted_mwh | annual_curtailment_loss | annual_ebitda_proxy | connect_now_value | wait_value | delta_npv |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for bus in result.buses:
        economics = qsts_bus_economics_proxy(result.request, bus)
        product_decision = selected_policy_verdict(
            bus,
            result.request,
            result.performance.evaluated_time_steps,
        )
        lines.append(
            "| "
            f"{bus.bus_id} | {product_decision} | {result.request.selected_policy} | "
            f"{bus.weighted_curtailment_mwh:.3f} | "
            f"{economics.annual_curtailment_loss_eur:.2f} | "
            f"{economics.annual_ebitda_proxy_eur:.2f} | "
            f"{economics.connect_now_value_eur:.2f} | "
            f"{economics.wait_value_eur:.2f} | {economics.delta_npv_eur:.2f} |"
        )
    return "\n".join(lines)


def render_contractual_summary_table(rows: tuple[Any, ...]) -> str:
    if not rows:
        return "No contractual envelope rows available."
    by_bus_direction: dict[tuple[int, str, str], list[Any]] = {}
    for row in rows:
        by_bus_direction.setdefault((row.bus_id, row.bus_name, row.direction), []).append(row)
    lines = [
        "| bus_id | direction | blocks | p10_min_mw | p10_max_mw | p10_mean_mw | p90_curtailment_max_mw | dominant_constraint |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for key, group in sorted(by_bus_direction.items(), key=lambda item: item[0]):
        bus_id, _bus_name, direction = key
        p10_values = [row.allowed_mw_p10 for row in group]
        p90_values = [row.curtailed_mw_p90 for row in group]
        lines.append(
            "| "
            f"{bus_id} | {direction} | {len(group)} | "
            f"{min(p10_values):.3f} | {max(p10_values):.3f} | "
            f"{(sum(p10_values) / len(p10_values)):.3f} | "
            f"{max(p90_values):.3f} | "
            f"{dominant_string(tuple(row.dominant_incremental_constraint for row in group)) or '-'} |"
        )
    return "\n".join(lines)


def render_contractual_envelope_table(rows: tuple[Any, ...]) -> str:
    if not rows:
        return "No contractual envelope rows available."
    lines = [
        "| bus_id | direction | season | time_block | allowed_mw_p10 | allowed_mw_p25 | allowed_mw_p50 | allowed_mw_min | curtailed_mw_p90 | dominant_constraint |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row.bus_id} | {row.direction} | {row.season} | {row.time_block} | "
            f"{row.allowed_mw_p10:.3f} | "
            f"{row.allowed_mw_p25:.3f} | "
            f"{row.allowed_mw_p50:.3f} | "
            f"{row.allowed_mw_min:.3f} | "
            f"{row.curtailed_mw_p90:.3f} | "
            f"{row.dominant_incremental_constraint or '-'} |"
        )
    return "\n".join(lines)


def render_envelope_comparison_table(comparisons: tuple[Any, ...]) -> str:
    lines = [
        "| bus_id | envelope | expected_curtailment_mwh | p50_curtailment_mw | p90_curtailment_mw | violation_hours | main_recurring_constraint |",
        "| ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for comparison in comparisons:
        lines.append(
            "| "
            f"{comparison.bus_id} | {comparison.envelope_name} | "
            f"{comparison.expected_curtailment_mwh:.3f} | "
            f"{comparison.p50_curtailment_mw:.3f} | "
            f"{comparison.p90_curtailment_mw:.3f} | "
            f"{comparison.violation_hours} | "
            f"{comparison.main_recurring_constraint or '-'} |"
        )
    return "\n".join(lines)


def static_vs_qsts_comparison_rows(
    result: Any,
    contractual_rows: tuple[Any, ...],
) -> tuple[dict[str, object], ...]:
    by_bus: dict[int, list[Any]] = {}
    for row in contractual_rows:
        by_bus.setdefault(row.bus_id, []).append(row)
    rows: list[dict[str, object]] = []
    for bus in result.buses:
        contract = by_bus.get(bus.bus_id, [])
        rows.append(
            {
                "bus_id": bus.bus_id,
                "bus_name": bus.bus_name,
                "qsts_verdict": bus.qsts_verdict,
                "static_firm_capacity_mw": f"{bus.static_firm_capacity_mw:.6f}",
                "static_conditional_capacity_mw": f"{bus.static_conditional_capacity_mw:.6f}",
                "contractual_allowed_mw_p10_min": format_contract_min(
                    [row.allowed_mw_p10 for row in contract]
                ),
                "contractual_allowed_mw_p25_min": format_contract_min(
                    [row.allowed_mw_p25 for row in contract]
                ),
                "contractual_allowed_mw_p50_min": format_contract_min(
                    [row.allowed_mw_p50 for row in contract]
                ),
                "contractual_allowed_mw_min": format_contract_min(
                    [row.allowed_mw_min for row in contract]
                ),
                "qsts_p90_curtailment_mw": f"{bus.curtailment.p90_mw:.6f}",
                "qsts_expected_curtailment_mwh": f"{bus.curtailment.expected_mwh:.6f}",
                "main_recurring_constraint": bus.main_recurring_constraint,
                "runtime_seconds": f"{result.performance.runtime_seconds:.6f}",
            }
        )
    return tuple(rows)


def selected_policy_verdict(
    bus: Any,
    request: Any,
    evaluated_time_steps: int = 0,
) -> str:
    max_event_hours, max_event_mwh = bus_max_curtailment_event(bus)
    rows = decision_frontier_rows(
        bus_id=bus.bus_id,
        bus_name=bus.bus_name,
        requested_mw=bus.requested_mw,
        qsts_p90_mw=bus.curtailment.p90_mw,
        weighted_curtailment_mwh=bus.weighted_curtailment_mwh,
        curtailment_energy_ratio=bus.curtailment_energy_ratio,
        max_event_hours=max_event_hours,
        max_event_mwh=max_event_mwh,
        validation_level=validation_level(request, evaluated_time_steps),
    )
    for row in rows:
        if row.policy == request.selected_policy:
            return row.frontier_verdict
    return bus.qsts_verdict


def bus_max_curtailment_event(bus: Any) -> tuple[int, float]:
    return max_curtailment_event(pd.DataFrame(asdict(record) for record in bus.hourly_records))


def max_curtailment_event(frame: pd.DataFrame) -> tuple[int, float]:
    if frame.empty:
        return 0, 0.0
    worst_index = frame.groupby("timestamp")["curtailed_mw"].idxmax()
    worst = frame.loc[worst_index].copy()
    worst["curtailed_mw"] = worst["curtailed_mw"].astype(float).clip(lower=0.0)
    worst["event_timestamp"] = worst["timestamp"].map(datetime_from_record_timestamp)
    worst = worst.sort_values("event_timestamp")
    max_hours = 0
    max_mwh = 0.0
    current_hours = 0
    current_mwh = 0.0
    previous_timestamp: datetime | None = None
    for item in worst.itertuples(index=False):
        timestamp = item.event_timestamp
        curtailed_mw = float(item.curtailed_mw)
        consecutive = (
            current_hours > 0
            and previous_timestamp is not None
            and (timestamp - previous_timestamp).total_seconds() == 3600
        )
        if curtailed_mw <= 1e-9:
            current_hours = 0
            current_mwh = 0.0
            previous_timestamp = timestamp
            continue
        if not consecutive:
            current_hours = 0
            current_mwh = 0.0
        current_hours += 1
        current_mwh += curtailed_mw
        max_hours = max(max_hours, current_hours)
        max_mwh = max(max_mwh, current_mwh)
        previous_timestamp = timestamp
    return max_hours, round(max_mwh, 6)


def datetime_from_record_timestamp(timestamp: str) -> datetime:
    try:
        return datetime.fromisoformat(str(timestamp))
    except ValueError:
        try:
            hour_index = int(timestamp)
        except (TypeError, ValueError):
            return datetime(2026, 1, 1)
        return datetime(2026, 1, 1) + timedelta(hours=hour_index % 8760)


def dominant_string(values: tuple[str, ...]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def contractual_p10_ranges(
    rows: tuple[Any, ...],
) -> dict[int, tuple[float, float]]:
    values_by_bus: dict[int, list[float]] = {}
    for row in rows:
        values_by_bus.setdefault(row.bus_id, []).append(row.allowed_mw_p10)
    return {
        bus_id: (min(values), max(values))
        for bus_id, values in values_by_bus.items()
        if values
    }


def format_contract_min(values: list[float]) -> str:
    if not values:
        return ""
    return f"{min(values):.6f}"


def format_optional_float(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}"


def write_run_manifest(
    result: Any,
    output_dir: Path,
    output_paths: dict[str, object],
    manifest_path: Path,
    command: Sequence[str] | None,
) -> None:
    manifest = {
        "schema_version": "qsts-run-manifest-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "command": list(command) if command is not None else None,
        "request": json_ready(asdict(result.request)),
        "constraint_settings": json_ready(asdict(result.settings)),
        "source": result.source,
        "outputs": manifest_outputs(output_dir, output_paths),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "thesegrid_version": package_version(),
        },
        "git": git_metadata(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_ready(value: object) -> object:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def manifest_outputs(output_dir: Path, output_paths: dict[str, object]) -> dict[str, object]:
    outputs: dict[str, object] = {}
    for key, value in output_paths.items():
        if isinstance(value, Path):
            outputs[key] = relative_or_string(value, output_dir)
        elif isinstance(value, list):
            outputs[key] = [
                relative_or_string(path, output_dir) if isinstance(path, Path) else str(path)
                for path in value
            ]
        else:
            outputs[key] = str(value)
    return outputs


def relative_or_string(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def package_version() -> str:
    try:
        return version("thesegrid")
    except PackageNotFoundError:
        return "editable"


def git_metadata() -> dict[str, object]:
    return {
        "commit": git_output("rev-parse", "HEAD"),
        "branch": git_output("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": git_dirty(),
    }


def git_output(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ("git", *args),
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def git_dirty() -> bool | None:
    try:
        completed = subprocess.run(
            ("git", "status", "--short"),
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(completed.stdout.strip())
