from __future__ import annotations

import csv
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from thesegrid.capacity import DispatchEvaluation, evaluate_dispatch
from thesegrid.contractual import (
    ContractualEnvelopeRow,
    synthesize_contractual_envelope,
)
from thesegrid.constraints import ConstraintSettings, check_constraints
from thesegrid.gabarits import GabaritKind, annual_timestamps, is_restricted
from thesegrid.models import ConstraintViolation, CurtailmentEstimate, Direction
from thesegrid.networks import ToyNetwork, load_network
from thesegrid.risk import estimate_curtailment


QSTS_RESULT_COLUMNS = (
    "rank",
    "bus_id",
    "bus_name",
    "qsts_verdict",
    "requested_mw",
    "static_firm_capacity_mw",
    "static_conditional_capacity_mw",
    "baseline_mode",
    "p90_curtailment_tolerance_mw",
    "feasible_hours",
    "violation_hours",
    "expected_curtailment_mwh",
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
    "qsts_verdict",
    "static_firm_capacity_mw",
    "static_conditional_capacity_mw",
    "qsts_p90_curtailment_mw",
    "qsts_expected_curtailment_mwh",
    "main_recurring_constraint",
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


@dataclass(frozen=True)
class QstsRequest:
    network_code: str
    screening_csv: Path
    requested_mw: float
    top_n: int = 10
    asset: str = "bess"
    tolerance_mw: float = 0.05
    start_hour: int = 0
    duration_hours: int | None = None
    sample_every_n_hours: int = 1
    stratified_sample: bool = False
    progress_every_n_hours: int = 0
    p90_curtailment_tolerance_mw: float = 0.0
    expected_curtailment_tolerance_mwh: float = 0.0
    storage_duration_hours: float = 4.0
    capex_eur_per_kw: float = 0.0
    fixed_opex_eur_per_kw_year: float = 0.0
    gross_revenue_eur_per_mw_year: float = 0.0
    curtailment_penalty_eur_per_mwh: float = 100.0
    reinforcement_wait_years: float = 5.0
    discount_rate: float = 0.08

    def __post_init__(self) -> None:
        if not self.network_code:
            raise ValueError("network_code must not be empty")
        if self.network_code == "toy":
            raise ValueError("QSTS requires a SimBench network; 'toy' is only for smoke tests")
        if self.requested_mw <= 0:
            raise ValueError("requested_mw must be positive")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")
        if self.asset.lower() != "bess":
            raise ValueError("V1 QSTS supports BESS assets only")
        if self.tolerance_mw <= 0:
            raise ValueError("tolerance_mw must be positive")
        if self.start_hour < 0:
            raise ValueError("start_hour must be non-negative")
        if self.duration_hours is not None and self.duration_hours <= 0:
            raise ValueError("duration_hours must be positive when provided")
        if self.sample_every_n_hours <= 0:
            raise ValueError("sample_every_n_hours must be positive")
        if self.progress_every_n_hours < 0:
            raise ValueError("progress_every_n_hours must be non-negative")
        if self.p90_curtailment_tolerance_mw < 0:
            raise ValueError("p90_curtailment_tolerance_mw must be non-negative")
        if self.expected_curtailment_tolerance_mwh < 0:
            raise ValueError("expected_curtailment_tolerance_mwh must be non-negative")
        if self.storage_duration_hours < 0:
            raise ValueError("storage_duration_hours must be non-negative")
        if self.capex_eur_per_kw < 0:
            raise ValueError("capex_eur_per_kw must be non-negative")
        if self.fixed_opex_eur_per_kw_year < 0:
            raise ValueError("fixed_opex_eur_per_kw_year must be non-negative")
        if self.gross_revenue_eur_per_mw_year < 0:
            raise ValueError("gross_revenue_eur_per_mw_year must be non-negative")
        if self.curtailment_penalty_eur_per_mwh < 0:
            raise ValueError("curtailment_penalty_eur_per_mwh must be non-negative")
        if self.reinforcement_wait_years < 0:
            raise ValueError("reinforcement_wait_years must be non-negative")
        if self.discount_rate < 0:
            raise ValueError("discount_rate must be non-negative")


@dataclass(frozen=True)
class QstsSelectedBus:
    rank: int
    bus_id: int
    bus_name: str
    firm_capacity_mw: float
    conditional_capacity_mw: float


@dataclass(frozen=True)
class QstsHourlyRecord:
    timestamp: str
    direction: Direction
    requested_mw: float
    feasible_mw: float
    curtailed_mw: float
    converged: bool
    min_vm_pu: float | None
    max_vm_pu: float | None
    max_loading_percent: float | None
    binding_constraint: str
    incremental_binding_constraint: str


@dataclass(frozen=True)
class QstsBusResult:
    rank: int
    bus_id: int
    bus_name: str
    qsts_verdict: str
    requested_mw: float
    static_firm_capacity_mw: float
    static_conditional_capacity_mw: float
    p90_curtailment_tolerance_mw: float
    feasible_hours: int
    violation_hours: int
    curtailment: CurtailmentEstimate
    main_recurring_constraint: str
    hourly_records: tuple[QstsHourlyRecord, ...]
    baseline_violating_hours: int = 0
    baseline_main_constraint: str = ""
    baseline_max_vm_pu: float | None = None
    baseline_max_loading_percent: float | None = None


@dataclass(frozen=True)
class QstsEnvelopeRecord:
    timestamp: str
    bus_id: int
    bus_name: str
    direction: Direction
    requested_mw: float
    allowed_mw: float
    curtailed_mw: float
    incremental_binding_constraint: str
    qsts_verdict_context: str


@dataclass(frozen=True)
class QstsEnvelopeSummaryRow:
    bus_id: int
    bus_name: str
    month: int
    hour: int
    direction: Direction
    allowed_mw_p50: float
    allowed_mw_p90: float
    allowed_mw_min: float
    curtailed_mw_p50: float
    curtailed_mw_p90: float
    dominant_incremental_constraint: str


@dataclass(frozen=True)
class QstsEnvelopeComparison:
    bus_id: int
    bus_name: str
    envelope_name: str
    expected_curtailment_mwh: float
    p50_curtailment_mw: float
    p90_curtailment_mw: float
    violation_hours: int
    main_recurring_constraint: str


@dataclass(frozen=True)
class QstsPerformanceStats:
    runtime_seconds: float = 0.0
    power_flow_calls: int = 0
    baseline_power_flow_calls: int = 0
    candidate_power_flow_calls: int = 0
    binary_search_count: int = 0
    baseline_cache_hits: int = 0
    baseline_cache_misses: int = 0
    evaluated_time_steps: int = 0
    evaluated_buses: int = 0


@dataclass(frozen=True)
class QstsEconomicsProxy:
    storage_duration_hours: float
    energy_capacity_mwh: float
    capex_eur: float
    annual_gross_revenue_eur: float
    annual_curtailment_loss_eur: float
    annual_fixed_opex_eur: float
    annual_ebitda_proxy_eur: float
    connect_now_value_eur: float
    wait_value_eur: float
    delta_npv_eur: float


@dataclass(frozen=True)
class QstsResult:
    request: QstsRequest
    buses: tuple[QstsBusResult, ...]
    source: str = "actual hourly power-flow validation"
    settings: ConstraintSettings = field(default_factory=ConstraintSettings)
    performance: QstsPerformanceStats = field(default_factory=QstsPerformanceStats)


@dataclass(frozen=True)
class QstsOutputPaths:
    results_csv_path: Path
    summary_path: Path
    run_manifest_path: Path
    investment_memo_path: Path
    performance_json_path: Path
    static_vs_qsts_comparison_csv_path: Path
    annual_validation_summary_path: Path
    investor_decision_csv_path: Path
    envelope_csv_path: Path
    envelope_summary_csv_path: Path
    contractual_envelope_csv_path: Path
    bus_detail_paths: tuple[Path, ...]


def select_top_buses_from_screening_csv(csv_path: Path, top_n: int) -> tuple[QstsSelectedBus, ...]:
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = sorted(csv.DictReader(handle), key=lambda row: int(row["rank"]))
    selected: list[QstsSelectedBus] = []
    for row in rows[:top_n]:
        selected.append(
            QstsSelectedBus(
                rank=int(row["rank"]),
                bus_id=int(row["bus_id"]),
                bus_name=row.get("bus_name", ""),
                firm_capacity_mw=float(row["firm_capacity_mw"]),
                conditional_capacity_mw=float(row["conditional_capacity_mw"]),
            )
        )
    return tuple(selected)


def load_simbench_power_profiles(net: object) -> dict[str, pd.DataFrame]:
    if not hasattr(net, "profiles"):
        raise ValueError("QSTS requires SimBench profiles on the pandapower network")

    try:
        import simbench as sb
    except ImportError as exc:
        raise ImportError("SimBench is required to load QSTS profiles") from exc

    profiles = {
        "load_p": _absolute_profile(sb, net, "load", "p_mw"),
        "load_q": _absolute_profile(sb, net, "load", "q_mvar"),
        "sgen_p": _absolute_profile(sb, net, "sgen", "p_mw"),
        "sgen_q": _absolute_profile(sb, net, "sgen", "q_mvar"),
        "gen_p": _absolute_profile(sb, net, "gen", "p_mw"),
        "storage_p": _absolute_profile(sb, net, "storage", "p_mw"),
    }
    if not any(not frame.empty for frame in profiles.values()):
        raise ValueError("QSTS requires at least one usable SimBench load, generation, or storage profile")
    return {name: _to_hourly_profile(frame) for name, frame in profiles.items()}


def qsts_curtailment_estimate(hourly_records: pd.DataFrame, timestep_hours: float = 1.0) -> CurtailmentEstimate:
    if hourly_records.empty:
        return estimate_curtailment(())
    worst_by_timestamp = hourly_records.groupby("timestamp")["curtailed_mw"].max()
    return estimate_curtailment(worst_by_timestamp.tolist(), timestep_hours=timestep_hours)


def classify_incremental_violations(
    candidate: dict[tuple[str, int, str], float],
    baseline: dict[tuple[str, int, str], float],
    tolerance: float = 1e-3,
) -> tuple[str, ...]:
    classifications: list[str] = []
    for key, candidate_value in candidate.items():
        baseline_value = baseline.get(key)
        element_type, element_id, metric = key
        label = f"{element_type}[{element_id}] {metric}"
        if baseline_value is None:
            classifications.append(f"new_candidate_violation: {label}={candidate_value:.3f}")
            continue
        if _is_worse(metric, candidate_value, baseline_value, tolerance):
            classifications.append(
                f"worsened_by_candidate: {label}={candidate_value:.3f} "
                f"baseline={baseline_value:.3f}"
            )
    return tuple(classifications)


def run_qsts(
    request: QstsRequest,
    net: object | None = None,
    settings: ConstraintSettings | None = None,
) -> QstsResult:
    started = time.perf_counter()
    settings = settings or ConstraintSettings()
    network = load_network(request.network_code) if net is None else net
    if isinstance(network, ToyNetwork) and request.network_code == "toy":
        raise ValueError("QSTS requires a SimBench network; 'toy' is only for smoke tests")
    profiles = load_simbench_power_profiles(network)
    selected_buses = select_top_buses_from_screening_csv(request.screening_csv, request.top_n)
    time_steps = _profile_time_steps(
        profiles,
        start_hour=request.start_hour,
        duration_hours=request.duration_hours,
        sample_every_n_hours=request.sample_every_n_hours,
        stratified_sample=request.stratified_sample,
    )
    if not time_steps:
        raise ValueError("QSTS requires at least one profile time step")

    baseline_cache: dict[int, _BaselineState] = {}
    tracker = _QstsPerformanceTracker(
        total_buses=len(selected_buses),
        total_time_steps=len(time_steps),
        progress_every_n_hours=request.progress_every_n_hours,
    )
    bus_results: list[QstsBusResult] = []
    for selected in selected_buses:
        bus_results.append(
            _run_qsts_for_bus(
                network,
                selected,
                requested_mw=request.requested_mw,
                profiles=profiles,
                time_steps=time_steps,
                settings=settings,
                tolerance_mw=request.tolerance_mw,
                p90_curtailment_tolerance_mw=request.p90_curtailment_tolerance_mw,
                expected_curtailment_tolerance_mwh=request.expected_curtailment_tolerance_mwh,
                baseline_cache=baseline_cache,
                tracker=tracker,
            )
        )
    return QstsResult(
        request=request,
        buses=tuple(bus_results),
        settings=settings,
        performance=tracker.to_stats(time.perf_counter() - started),
    )


def write_qsts_outputs(
    result: QstsResult,
    output_dir: Path,
    command: Sequence[str] | None = None,
) -> QstsOutputPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    results_csv = output_dir / "qsts_results.csv"
    summary_path = output_dir / "qsts_summary.md"
    run_manifest_path = output_dir / "run_manifest.json"
    investment_memo_path = output_dir / "investment_memo.md"
    performance_json_path = output_dir / "qsts_performance.json"
    static_vs_qsts_comparison_csv = output_dir / "static_vs_qsts_comparison.csv"
    annual_validation_summary_path = output_dir / "annual_validation_summary.md"
    investor_decision_csv = output_dir / "investor_decision.csv"
    envelope_csv = output_dir / "qsts_envelope.csv"
    envelope_summary_csv = output_dir / "qsts_envelope_summary.csv"
    contractual_envelope_csv = output_dir / "contractual_envelope.csv"
    detail_paths: list[Path] = []

    with results_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QSTS_RESULT_COLUMNS)
        writer.writeheader()
        for bus in result.buses:
            writer.writerow(_bus_result_row(bus))

    with investor_decision_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVESTOR_DECISION_COLUMNS)
        writer.writeheader()
        for bus in result.buses:
            writer.writerow(_investor_decision_row(bus))

    for bus in result.buses:
        detail_path = output_dir / f"qsts_bus_{bus.bus_id}.csv"
        with detail_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=QSTS_DETAIL_COLUMNS)
            writer.writeheader()
            for record in bus.hourly_records:
                writer.writerow(asdict(record))
        detail_paths.append(detail_path)

    envelope_records = qsts_envelope_records(result)
    with envelope_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QSTS_ENVELOPE_COLUMNS)
        writer.writeheader()
        for record in envelope_records:
            writer.writerow(_envelope_record_row(record))

    with envelope_summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QSTS_ENVELOPE_SUMMARY_COLUMNS)
        writer.writeheader()
        for row in summarize_qsts_envelope(envelope_records):
            writer.writerow(_envelope_summary_row(row))

    contractual = synthesize_contractual_envelope(envelope_records)
    with contractual_envelope_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CONTRACTUAL_ENVELOPE_COLUMNS)
        writer.writeheader()
        for row in contractual.rows:
            writer.writerow(_contractual_envelope_row(row))

    with static_vs_qsts_comparison_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=STATIC_VS_QSTS_COMPARISON_COLUMNS)
        writer.writeheader()
        for row in _static_vs_qsts_comparison_rows(result, contractual.rows):
            writer.writerow(row)

    summary_path.write_text(render_qsts_summary(result), encoding="utf-8")
    investment_memo_path.write_text(render_qsts_investment_memo(result), encoding="utf-8")
    annual_validation_summary_path.write_text(
        render_annual_validation_summary(result),
        encoding="utf-8",
    )
    performance_json_path.write_text(
        json.dumps(_json_ready(asdict(result.performance)), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_run_manifest(
        result=result,
        output_dir=output_dir,
        output_paths={
            "qsts_results": results_csv,
            "qsts_summary": summary_path,
            "investment_memo": investment_memo_path,
            "qsts_performance": performance_json_path,
            "static_vs_qsts_comparison": static_vs_qsts_comparison_csv,
            "annual_validation_summary": annual_validation_summary_path,
            "investor_decision": investor_decision_csv,
            "qsts_envelope": envelope_csv,
            "qsts_envelope_summary": envelope_summary_csv,
            "contractual_envelope": contractual_envelope_csv,
            "bus_details": detail_paths,
        },
        manifest_path=run_manifest_path,
        command=command,
    )
    return QstsOutputPaths(
        results_csv_path=results_csv,
        summary_path=summary_path,
        run_manifest_path=run_manifest_path,
        investment_memo_path=investment_memo_path,
        performance_json_path=performance_json_path,
        static_vs_qsts_comparison_csv_path=static_vs_qsts_comparison_csv,
        annual_validation_summary_path=annual_validation_summary_path,
        investor_decision_csv_path=investor_decision_csv,
        envelope_csv_path=envelope_csv,
        envelope_summary_csv_path=envelope_summary_csv,
        contractual_envelope_csv_path=contractual_envelope_csv,
        bus_detail_paths=tuple(detail_paths),
    )


def qsts_envelope_records(result: QstsResult) -> tuple[QstsEnvelopeRecord, ...]:
    records: list[QstsEnvelopeRecord] = []
    for bus in result.buses:
        for hourly in bus.hourly_records:
            records.append(
                QstsEnvelopeRecord(
                    timestamp=hourly.timestamp,
                    bus_id=bus.bus_id,
                    bus_name=bus.bus_name,
                    direction=hourly.direction,
                    requested_mw=hourly.requested_mw,
                    allowed_mw=hourly.feasible_mw,
                    curtailed_mw=hourly.curtailed_mw,
                    incremental_binding_constraint=hourly.incremental_binding_constraint,
                    qsts_verdict_context=bus.qsts_verdict,
                )
            )
    return tuple(records)


def summarize_qsts_envelope(
    records: tuple[QstsEnvelopeRecord, ...],
) -> tuple[QstsEnvelopeSummaryRow, ...]:
    if not records:
        return ()
    frame = pd.DataFrame(asdict(record) for record in records)
    month_hour = frame["timestamp"].map(_month_hour_from_timestamp)
    frame["month"] = [month for month, _hour in month_hour]
    frame["hour"] = [hour for _month, hour in month_hour]
    grouped = frame.groupby(["bus_id", "bus_name", "month", "hour", "direction"], sort=True)
    rows: list[QstsEnvelopeSummaryRow] = []
    for key, group in grouped:
        bus_id, bus_name, month, hour, direction = key
        rows.append(
            QstsEnvelopeSummaryRow(
                bus_id=int(bus_id),
                bus_name=str(bus_name),
                month=int(month),
                hour=int(hour),
                direction=direction,
                allowed_mw_p50=round(float(group["allowed_mw"].quantile(0.50)), 6),
                allowed_mw_p90=round(float(group["allowed_mw"].quantile(0.90)), 6),
                allowed_mw_min=round(float(group["allowed_mw"].min()), 6),
                curtailed_mw_p50=round(float(group["curtailed_mw"].quantile(0.50)), 6),
                curtailed_mw_p90=round(float(group["curtailed_mw"].quantile(0.90)), 6),
                dominant_incremental_constraint=_dominant_string(
                    tuple(group["incremental_binding_constraint"])
                ),
            )
        )
    return tuple(rows)


def compare_qsts_envelopes(result: QstsResult) -> tuple[QstsEnvelopeComparison, ...]:
    comparisons: list[QstsEnvelopeComparison] = []
    for bus in result.buses:
        comparisons.extend(_bus_envelope_comparisons(bus))
    return tuple(comparisons)


def render_qsts_summary(result: QstsResult) -> str:
    if not result.buses:
        top_table = "No buses selected for QSTS validation."
        investor_table = "No buses selected for investor decision table."
        baseline_table = "No baseline diagnostics available."
        comparison_table = "No envelope comparison available."
        contractual_table = "No contractual envelope available."
    else:
        top_table = _render_qsts_table(result.buses)
        investor_table = _render_investor_decision_table(result.buses)
        baseline_table = _render_baseline_table(result.buses)
        comparison_table = _render_envelope_comparison_table(compare_qsts_envelopes(result))
        contractual_table = _render_contractual_envelope_table(
            synthesize_contractual_envelope(qsts_envelope_records(result)).rows
        )
    return f"""# QSTS Top-N BESS Validation Summary

This report is based on {result.source}. It remains an early-stage buyer-side decision aid and does not replace an official grid-connection study.

## Request

- network_code: {result.request.network_code}
- requested_mw: {result.request.requested_mw:.3f}
- screening_csv: {result.request.screening_csv}
- top_n: {result.request.top_n}
- start_hour: {result.request.start_hour}
- duration_hours: {result.request.duration_hours if result.request.duration_hours is not None else "all available"}
- sample_every_n_hours: {result.request.sample_every_n_hours}
- stratified_sample: {result.request.stratified_sample}
- tolerance_mw: {result.request.tolerance_mw:.3f}
- p90_curtailment_tolerance_mw: {result.request.p90_curtailment_tolerance_mw:.3f}
- expected_curtailment_tolerance_mwh: {result.request.expected_curtailment_tolerance_mwh:.3f}
- voltage_min_pu: {result.settings.min_vm_pu:.3f}
- voltage_max_pu: {result.settings.max_vm_pu:.3f}
- max_loading_percent: {result.settings.max_loading_percent:.3f}
- evaluated_buses: {len(result.buses)}
- baseline_mode: pre-existing violations ignored unless worsened by candidate

## Results

{top_table}

## Investor Decision Table

{investor_table}

## Baseline Summary

{baseline_table}

## Envelope Comparison

{comparison_table}

## Contractual Envelope

{contractual_table}

## Interpretation

- QSTS results replay time-varying network operating points before checking BESS injection and withdrawal.
- QSTS-derived envelope rows are extracted from the hourly feasible MW already computed by QSTS; no extra power-flow pass is hidden in the export step.
- Contractual envelope rows summarize QSTS-derived allowed MW into RTE-inspired V1 seasons and time blocks using P10 allowed MW as the recommended conservative value.
- Verdicts are baseline-aware: pre-existing network violations are separated from new or worsened candidate violations.
- Static proxy curtailment and QSTS curtailment are not equivalent; QSTS is the higher-evidence validation layer.
- The study still excludes short-circuit, protection, dynamic stability, N-1 security, harmonics, and official operator planning criteria.
"""


def render_qsts_investment_memo(result: QstsResult) -> str:
    if not result.buses:
        primary = "No candidate bus was selected for QSTS validation."
        investor_table = "No investor decision rows available."
        contractual_summary = "No contractual envelope rows available."
        contractual_detail = "No contractual envelope rows available."
    else:
        top_bus = result.buses[0]
        primary = (
            f"Bus {top_bus.bus_id} ({top_bus.bus_name or 'unnamed'}) is the top-ranked "
            f"QSTS candidate with verdict `{top_bus.qsts_verdict}` at "
            f"{top_bus.requested_mw:.3f} MW."
        )
        contractual_rows = synthesize_contractual_envelope(qsts_envelope_records(result)).rows
        investor_table = _render_qsts_investment_table(result.buses, contractual_rows)
        contractual_summary = _render_contractual_summary_table(contractual_rows)
        contractual_detail = _render_contractual_envelope_table(contractual_rows)
    economics = _qsts_economics_proxy(result)
    return f"""# QSTS BESS Investment Memo

This memo is an early-stage buyer-side decision aid for BESS flexible connection pre-feasibility. It does not replace an official grid-connection study.

## Primary Recommendation

{primary}

## Request

- network_code: {result.request.network_code}
- requested_mw: {result.request.requested_mw:.3f}
- screening_csv: {result.request.screening_csv}
- evaluated_buses: {len(result.buses)}
- baseline_mode: pre-existing violations ignored unless worsened by candidate
- qsts_p90_tolerance_mw: {result.request.p90_curtailment_tolerance_mw:.3f}
- qsts_expected_curtailment_tolerance_mwh: {result.request.expected_curtailment_tolerance_mwh:.3f}

## Investor Decision

{investor_table}

## Contractual Envelope Summary

{contractual_summary}

## Contractual Envelope Detail

{contractual_detail}

## Economics Proxy

- storage_duration_hours: {economics.storage_duration_hours:.3f}
- energy_capacity_mwh: {economics.energy_capacity_mwh:.3f}
- capex_eur: {economics.capex_eur:.2f}
- annual_gross_revenue_eur: {economics.annual_gross_revenue_eur:.2f}
- annual_curtailment_loss_eur: {economics.annual_curtailment_loss_eur:.2f}
- annual_fixed_opex_eur: {economics.annual_fixed_opex_eur:.2f}
- annual_ebitda_proxy_eur: {economics.annual_ebitda_proxy_eur:.2f}
- connect_now_value_eur: {economics.connect_now_value_eur:.2f}
- wait_value_eur: {economics.wait_value_eur:.2f}
- delta_npv_eur: {economics.delta_npv_eur:.2f}

## Interpretation

- Static screening is a proxy ranking layer; QSTS is the hourly power-flow validation layer.
- The contractual envelope is synthesized from QSTS allowed MW by direction, V1 season, and fixed time block.
- `contract_p10_min_mw` is the tightest conservative contractual MW across the synthesized blocks for a bus.
- Remaining exclusions: short-circuit, protection, dynamic stability, N-1 security, harmonics, and official operator planning criteria.
"""


def render_annual_validation_summary(result: QstsResult) -> str:
    return f"""# Annual Validation Summary

This file summarizes the QSTS validation bundle. It can be used for full-year or sampled annual campaigns; check `run_manifest.json` for the exact sampling mode and duration.

## Runtime

- runtime_seconds: {result.performance.runtime_seconds:.3f}
- power_flow_calls: {result.performance.power_flow_calls}
- baseline_power_flow_calls: {result.performance.baseline_power_flow_calls}
- candidate_power_flow_calls: {result.performance.candidate_power_flow_calls}
- binary_search_count: {result.performance.binary_search_count}
- evaluated_time_steps: {result.performance.evaluated_time_steps}
- evaluated_buses: {result.performance.evaluated_buses}

## Bundle

- static_vs_qsts_comparison.csv
- qsts_performance.json
- contractual_envelope.csv
- qsts_results.csv
- run_manifest.json
"""


def _run_qsts_for_bus(
    net: object,
    selected: QstsSelectedBus,
    requested_mw: float,
    profiles: dict[str, pd.DataFrame],
    time_steps: tuple[int, ...],
    settings: ConstraintSettings,
    tolerance_mw: float,
    p90_curtailment_tolerance_mw: float,
    expected_curtailment_tolerance_mwh: float,
    baseline_cache: dict[int, _BaselineState] | None = None,
    tracker: _QstsPerformanceTracker | None = None,
) -> QstsBusResult:
    records: list[QstsHourlyRecord] = []
    constraint_counts: dict[str, int] = {}
    baseline_constraint_counts: dict[str, int] = {}
    baseline_violating_hours = 0
    baseline_max_vm_pu: float | None = None
    baseline_max_loading_percent: float | None = None
    timestamps = _timestamps_for_steps(time_steps)
    baseline_cache = baseline_cache if baseline_cache is not None else {}
    tracker = tracker if tracker is not None else _QstsPerformanceTracker()
    tracker.evaluated_buses += 1

    with _QstsDispatchEvaluator(net, selected.bus_id, settings, tracker) as evaluator:
        for position, time_step in enumerate(time_steps):
            _apply_profiles(net, profiles, time_step)
            evaluator.reset_candidate()
            if time_step not in baseline_cache:
                tracker.baseline_cache_misses += 1
                baseline_cache[time_step] = _baseline_state(net, selected.bus_id, settings, tracker)
            else:
                tracker.baseline_cache_hits += 1
            baseline_state = baseline_cache[time_step]
            baseline = baseline_state.violations
            if baseline:
                baseline_violating_hours += 1
                if baseline_state.binding_constraint:
                    baseline_constraint_counts[baseline_state.binding_constraint] = (
                        baseline_constraint_counts.get(baseline_state.binding_constraint, 0) + 1
                    )
            baseline_max_vm_pu = _max_optional(baseline_max_vm_pu, baseline_state.max_vm_pu)
            baseline_max_loading_percent = _max_optional(
                baseline_max_loading_percent,
                baseline_state.max_loading_percent,
            )
            timestamp = timestamps[position]
            for direction in ("injection", "withdrawal"):
                requested = _evaluate_incremental_dispatch(
                    evaluator,
                    direction,
                    requested_mw,
                    baseline,
                )
                if requested.incrementally_feasible:
                    feasible_mw = requested_mw
                    incremental_violations = requested.incremental_violations
                else:
                    tracker.binary_search_count += 1
                    feasible_mw = _find_max_feasible_with_infeasible_high(
                        upper_mw=requested_mw,
                        is_feasible=lambda mw, direction=direction: _evaluate_incremental_dispatch(
                            evaluator,
                            direction,
                            mw,
                            baseline,
                        ).incrementally_feasible,
                        tolerance_mw=tolerance_mw,
                    )
                    incremental_violations = requested.incremental_violations
                    if incremental_violations:
                        description = incremental_violations[0]
                        constraint_counts[description] = constraint_counts.get(description, 0) + 1
                records.append(
                    QstsHourlyRecord(
                        timestamp=str(timestamp),
                        direction=direction,
                        requested_mw=round(requested_mw, 6),
                        feasible_mw=round(feasible_mw, 6),
                        curtailed_mw=round(max(0.0, requested_mw - feasible_mw), 6),
                        converged=requested.converged,
                        min_vm_pu=requested.min_vm_pu,
                        max_vm_pu=requested.max_vm_pu,
                        max_loading_percent=requested.max_loading_percent,
                        binding_constraint=requested.binding_constraint,
                        incremental_binding_constraint=(
                            incremental_violations[0] if incremental_violations else ""
                        ),
                    )
                )
            tracker.record_time_step()

    hourly_frame = pd.DataFrame(asdict(record) for record in records)
    curtailment = qsts_curtailment_estimate(hourly_frame)
    total_hours = len(time_steps)
    feasible_hours = total_hours - curtailment.expected_hours
    qsts_verdict = _qsts_verdict(
        curtailment,
        p90_tolerance_mw=p90_curtailment_tolerance_mw,
        mwh_tolerance=expected_curtailment_tolerance_mwh,
    )
    return QstsBusResult(
        rank=selected.rank,
        bus_id=selected.bus_id,
        bus_name=selected.bus_name,
        qsts_verdict=qsts_verdict,
        requested_mw=round(requested_mw, 6),
        static_firm_capacity_mw=round(selected.firm_capacity_mw, 6),
        static_conditional_capacity_mw=round(selected.conditional_capacity_mw, 6),
        p90_curtailment_tolerance_mw=round(p90_curtailment_tolerance_mw, 6),
        feasible_hours=feasible_hours,
        violation_hours=curtailment.expected_hours,
        curtailment=curtailment,
        main_recurring_constraint=_main_recurring_constraint(constraint_counts),
        hourly_records=tuple(records),
        baseline_violating_hours=baseline_violating_hours,
        baseline_main_constraint=_main_recurring_constraint(baseline_constraint_counts),
        baseline_max_vm_pu=baseline_max_vm_pu,
        baseline_max_loading_percent=baseline_max_loading_percent,
    )


def _absolute_profile(sb: Any, net: object, element: str, column: str) -> pd.DataFrame:
    table = getattr(net, element, None)
    if table is None or table.empty or column not in table:
        return pd.DataFrame()
    try:
        return sb.get_absolute_profiles_from_relative_profiles(
            net,
            element,
            column,
            time_as_index=False,
        )
    except Exception as exc:
        raise ValueError(
            f"QSTS could not load SimBench profile for {element}.{column}"
        ) from exc


def _to_hourly_profile(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or len(frame) in {8760, 8784}:
        return frame
    if len(frame) % 4 == 0:
        factor = 4
    elif len(frame) % 8760 == 0:
        factor = len(frame) // 8760
    else:
        return frame
    grouped = frame.reset_index(drop=True).groupby(lambda idx: idx // factor).mean()
    grouped.index = range(len(grouped))
    return grouped


def _profile_time_steps(
    profiles: dict[str, pd.DataFrame],
    start_hour: int = 0,
    duration_hours: int | None = None,
    sample_every_n_hours: int = 1,
    stratified_sample: bool = False,
) -> tuple[int, ...]:
    lengths = [len(frame) for frame in profiles.values() if not frame.empty]
    if not lengths:
        return ()
    available = min(lengths)
    if start_hour >= available:
        return ()
    end = available if duration_hours is None else min(available, start_hour + duration_hours)
    if stratified_sample:
        stratified = _stratified_time_steps(start_hour, end)
        if stratified:
            return stratified
    return tuple(range(start_hour, end, sample_every_n_hours))


def _stratified_time_steps(start_hour: int, end_hour: int) -> tuple[int, ...]:
    timestamps = annual_timestamps(2026)
    block_hours = (0, 7, 10, 13, 17, 18, 21)
    selected: list[int] = []
    seen: set[tuple[int, int]] = set()
    upper = min(end_hour, len(timestamps))
    for hour_index in range(start_hour, upper):
        timestamp = timestamps[hour_index]
        key = (timestamp.month, timestamp.hour)
        if timestamp.hour not in block_hours or key in seen:
            continue
        seen.add(key)
        selected.append(hour_index)
    return tuple(selected)


def _timestamps_for_steps(time_steps: tuple[int, ...]) -> tuple[str | int, ...]:
    timestamps = annual_timestamps(2026)
    if all(0 <= time_step < len(timestamps) for time_step in time_steps):
        return tuple(timestamps[time_step].isoformat() for time_step in time_steps)
    return time_steps


def _apply_profiles(net: object, profiles: dict[str, pd.DataFrame], time_step: int) -> None:
    _apply_profile(net, "load", "p_mw", profiles["load_p"], time_step)
    _apply_profile(net, "load", "q_mvar", profiles["load_q"], time_step)
    _apply_profile(net, "sgen", "p_mw", profiles["sgen_p"], time_step)
    _apply_profile(net, "sgen", "q_mvar", profiles["sgen_q"], time_step)
    _apply_profile(net, "gen", "p_mw", profiles["gen_p"], time_step)
    _apply_profile(net, "storage", "p_mw", profiles["storage_p"], time_step)


def _apply_profile(
    net: object,
    element: str,
    column: str,
    profile: pd.DataFrame,
    time_step: int,
) -> None:
    table = getattr(net, element, None)
    if table is None or profile.empty or column not in table:
        return
    values = profile.iloc[time_step]
    for element_id, value in values.items():
        if element_id in table.index:
            table.at[element_id, column] = float(value)


@dataclass(frozen=True)
class _IncrementalDispatchEvaluation:
    incrementally_feasible: bool
    incremental_violations: tuple[str, ...]
    binding_constraint: str
    min_vm_pu: float | None
    max_vm_pu: float | None
    max_loading_percent: float | None
    converged: bool


@dataclass(frozen=True)
class _BaselineState:
    violations: dict[tuple[str, int, str], float]
    binding_constraint: str
    min_vm_pu: float | None
    max_vm_pu: float | None
    max_loading_percent: float | None
    converged: bool


class _QstsPerformanceTracker:
    def __init__(
        self,
        total_buses: int = 0,
        total_time_steps: int = 0,
        progress_every_n_hours: int = 0,
    ) -> None:
        self.total_buses = total_buses
        self.total_time_steps = total_time_steps
        self.progress_every_n_hours = progress_every_n_hours
        self.power_flow_calls = 0
        self.baseline_power_flow_calls = 0
        self.candidate_power_flow_calls = 0
        self.binary_search_count = 0
        self.baseline_cache_hits = 0
        self.baseline_cache_misses = 0
        self.evaluated_time_steps = 0
        self.evaluated_buses = 0

    def record_baseline_power_flow(self) -> None:
        self.power_flow_calls += 1
        self.baseline_power_flow_calls += 1

    def record_candidate_power_flow(self) -> None:
        self.power_flow_calls += 1
        self.candidate_power_flow_calls += 1

    def record_time_step(self) -> None:
        self.evaluated_time_steps += 1
        if (
            self.progress_every_n_hours > 0
            and self.evaluated_time_steps % self.progress_every_n_hours == 0
        ):
            total = self.total_buses * self.total_time_steps
            print(
                f"qsts progress: {self.evaluated_time_steps}/{total} bus-hours evaluated",
                file=sys.stderr,
            )

    def to_stats(self, runtime_seconds: float) -> QstsPerformanceStats:
        return QstsPerformanceStats(
            runtime_seconds=round(runtime_seconds, 6),
            power_flow_calls=self.power_flow_calls,
            baseline_power_flow_calls=self.baseline_power_flow_calls,
            candidate_power_flow_calls=self.candidate_power_flow_calls,
            binary_search_count=self.binary_search_count,
            baseline_cache_hits=self.baseline_cache_hits,
            baseline_cache_misses=self.baseline_cache_misses,
            evaluated_time_steps=self.evaluated_time_steps,
            evaluated_buses=self.evaluated_buses,
        )


class _QstsDispatchEvaluator:
    def __init__(
        self,
        net: object,
        bus_id: int,
        settings: ConstraintSettings,
        tracker: _QstsPerformanceTracker,
    ) -> None:
        self.net = net
        self.bus_id = bus_id
        self.settings = settings
        self.tracker = tracker
        self._sgen_id: int | None = None
        self._load_id: int | None = None

    def __enter__(self) -> _QstsDispatchEvaluator:
        if isinstance(self.net, ToyNetwork):
            return self
        import pandapower as pp

        self._sgen_id = int(
            pp.create_sgen(
                self.net,
                bus=self.bus_id,
                p_mw=0.0,
                q_mvar=0.0,
                name="candidate_bess_injection_qsts",
            )
        )
        self._load_id = int(
            pp.create_load(
                self.net,
                bus=self.bus_id,
                p_mw=0.0,
                q_mvar=0.0,
                name="candidate_bess_withdrawal_qsts",
            )
        )
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        if isinstance(self.net, ToyNetwork):
            return
        if self._sgen_id is not None and self._sgen_id in self.net.sgen.index:
            self.net.sgen.drop(index=self._sgen_id, inplace=True)
        if self._load_id is not None and self._load_id in self.net.load.index:
            self.net.load.drop(index=self._load_id, inplace=True)

    def reset_candidate(self) -> None:
        if isinstance(self.net, ToyNetwork):
            return
        if self._sgen_id is not None and self._sgen_id in self.net.sgen.index:
            self.net.sgen.at[self._sgen_id, "p_mw"] = 0.0
            self.net.sgen.at[self._sgen_id, "q_mvar"] = 0.0
        if self._load_id is not None and self._load_id in self.net.load.index:
            self.net.load.at[self._load_id, "p_mw"] = 0.0
            self.net.load.at[self._load_id, "q_mvar"] = 0.0

    def evaluate(self, direction: Direction, mw: float) -> DispatchEvaluation:
        self.tracker.record_candidate_power_flow()
        if isinstance(self.net, ToyNetwork):
            return evaluate_dispatch(self.net, self.bus_id, direction, mw, self.settings)

        import pandapower as pp

        self.reset_candidate()
        if direction == "injection" and self._sgen_id is not None:
            self.net.sgen.at[self._sgen_id, "p_mw"] = mw
        elif direction == "withdrawal" and self._load_id is not None:
            self.net.load.at[self._load_id, "p_mw"] = mw
        try:
            pp.runpp(self.net, numba=False)
        except Exception:
            return DispatchEvaluation(
                feasible=False,
                violations=(
                    ConstraintViolation(
                        element_type="power_flow",
                        element_id=-1,
                        element_name="pandapower",
                        metric="converged",
                        value=0.0,
                        limit=1.0,
                    ),
                ),
            )
        violations = tuple(check_constraints(self.net, self.settings))
        return DispatchEvaluation(
            feasible=not violations,
            violations=violations,
            min_vm_pu=_result_min(self.net, "res_bus", "vm_pu"),
            max_vm_pu=_result_max(self.net, "res_bus", "vm_pu"),
            max_loading_percent=_max_loading_percent(self.net),
        )


def _baseline_state(
    net: object,
    bus_id: int,
    settings: ConstraintSettings,
    tracker: _QstsPerformanceTracker | None = None,
) -> _BaselineState:
    if tracker is not None:
        tracker.record_baseline_power_flow()
    if isinstance(net, ToyNetwork):
        evaluation = evaluate_dispatch(net, bus_id, "injection", 0.0, settings)
        return _BaselineState(
            violations=_violation_snapshot(evaluation.violations),
            binding_constraint=evaluation.violations[0].description if evaluation.violations else "",
            min_vm_pu=evaluation.min_vm_pu,
            max_vm_pu=evaluation.max_vm_pu,
            max_loading_percent=evaluation.max_loading_percent,
            converged=not any(
                violation.element_type == "power_flow" for violation in evaluation.violations
            ),
        )

    import pandapower as pp

    try:
        pp.runpp(net, numba=False)
    except Exception:
        return _BaselineState(
            violations={("power_flow", -1, "converged"): 0.0},
            binding_constraint="power_flow[-1] pandapower converged=0.000 limit=1.000",
            min_vm_pu=None,
            max_vm_pu=None,
            max_loading_percent=None,
            converged=False,
        )

    violations = tuple(check_constraints(net, settings))
    return _BaselineState(
        violations=_violation_snapshot(violations),
        binding_constraint=violations[0].description if violations else "",
        min_vm_pu=_result_min(net, "res_bus", "vm_pu"),
        max_vm_pu=_result_max(net, "res_bus", "vm_pu"),
        max_loading_percent=_max_loading_percent(net),
        converged=True,
    )


def _baseline_violation_snapshot(
    net: object,
    bus_id: int,
    settings: ConstraintSettings,
) -> dict[tuple[str, int, str], float]:
    return _baseline_state(net, bus_id, settings).violations


def _evaluate_incremental_dispatch(
    evaluator: _QstsDispatchEvaluator,
    direction: Direction,
    mw: float,
    baseline: dict[tuple[str, int, str], float],
) -> _IncrementalDispatchEvaluation:
    evaluation = evaluator.evaluate(direction, mw)
    candidate = _violation_snapshot(evaluation.violations)
    incremental = classify_incremental_violations(candidate, baseline)
    return _IncrementalDispatchEvaluation(
        incrementally_feasible=not incremental,
        incremental_violations=incremental,
        binding_constraint=evaluation.violations[0].description if evaluation.violations else "",
        min_vm_pu=evaluation.min_vm_pu,
        max_vm_pu=evaluation.max_vm_pu,
        max_loading_percent=evaluation.max_loading_percent,
        converged=not any(
            violation.element_type == "power_flow" for violation in evaluation.violations
        ),
    )


def _find_max_feasible_with_infeasible_high(
    upper_mw: float,
    is_feasible: Any,
    tolerance_mw: float,
) -> float:
    low = 0.0
    high = upper_mw
    while high - low > tolerance_mw:
        midpoint = (low + high) / 2
        if is_feasible(midpoint):
            low = midpoint
        else:
            high = midpoint
    return low


def _violation_snapshot(
    violations: tuple[ConstraintViolation, ...],
) -> dict[tuple[str, int, str], float]:
    return {
        (violation.element_type, violation.element_id, violation.metric): violation.value
        for violation in violations
    }


def _month_hour_from_timestamp(timestamp: str) -> tuple[int, int]:
    try:
        parsed = datetime.fromisoformat(str(timestamp))
    except ValueError:
        try:
            hour_index = int(timestamp)
        except (TypeError, ValueError):
            return (0, 0)
        return (0, hour_index % 24)
    return (parsed.month, parsed.hour)


def _datetime_from_record_timestamp(timestamp: str) -> datetime:
    try:
        return datetime.fromisoformat(str(timestamp))
    except ValueError:
        try:
            hour_index = int(timestamp)
        except (TypeError, ValueError):
            return annual_timestamps(2026)[0]
        timestamps = annual_timestamps(2026)
        if 0 <= hour_index < len(timestamps):
            return timestamps[hour_index]
        return timestamps[hour_index % len(timestamps)]


def _bus_envelope_comparisons(bus: QstsBusResult) -> tuple[QstsEnvelopeComparison, ...]:
    return (
        _comparison_for_static_capacity(
            bus,
            envelope_name=GabaritKind.FIRM_ONLY.value,
            allowed_capacity_mw=bus.static_firm_capacity_mw,
            constraint_label="static firm capacity",
        ),
        _comparison_for_static_capacity(
            bus,
            envelope_name="static custom envelope",
            allowed_capacity_mw=bus.static_conditional_capacity_mw,
            constraint_label="static custom capacity",
        ),
        _comparison_for_gabarit(bus, GabaritKind.RTE_INJECTION),
        _comparison_for_gabarit(bus, GabaritKind.RTE_WITHDRAWAL),
        _comparison_from_records(
            bus,
            "QSTS-derived envelope",
            tuple((record.timestamp, record.curtailed_mw, record.incremental_binding_constraint) for record in bus.hourly_records),
        ),
    )


def _comparison_for_static_capacity(
    bus: QstsBusResult,
    envelope_name: str,
    allowed_capacity_mw: float,
    constraint_label: str,
) -> QstsEnvelopeComparison:
    rows = tuple(
        (
            record.timestamp,
            max(0.0, record.requested_mw - min(record.requested_mw, allowed_capacity_mw)),
            constraint_label,
        )
        for record in bus.hourly_records
    )
    return _comparison_from_records(bus, envelope_name, rows)


def _comparison_for_gabarit(
    bus: QstsBusResult,
    gabarit: GabaritKind,
) -> QstsEnvelopeComparison:
    rows: list[tuple[str, float, str]] = []
    for record in bus.hourly_records:
        timestamp = _datetime_from_record_timestamp(record.timestamp)
        allowed = (
            0.0
            if is_restricted(timestamp, record.direction, gabarit)
            else min(record.requested_mw, bus.static_conditional_capacity_mw)
        )
        curtailed = max(0.0, record.requested_mw - allowed)
        rows.append((record.timestamp, curtailed, gabarit.value))
    return _comparison_from_records(bus, gabarit.value, tuple(rows))


def _comparison_from_records(
    bus: QstsBusResult,
    envelope_name: str,
    rows: tuple[tuple[str, float, str], ...],
) -> QstsEnvelopeComparison:
    if not rows:
        curtailment = estimate_curtailment(())
        main_constraint = ""
    else:
        frame = pd.DataFrame(rows, columns=["timestamp", "curtailed_mw", "constraint"])
        worst_by_timestamp = frame.groupby("timestamp")["curtailed_mw"].max()
        curtailment = estimate_curtailment(worst_by_timestamp.tolist())
        constrained = frame.loc[frame["curtailed_mw"] > 1e-9, "constraint"].tolist()
        main_constraint = _dominant_string(tuple(str(value) for value in constrained))
    return QstsEnvelopeComparison(
        bus_id=bus.bus_id,
        bus_name=bus.bus_name,
        envelope_name=envelope_name,
        expected_curtailment_mwh=round(curtailment.expected_mwh, 6),
        p50_curtailment_mw=round(curtailment.p50_mw, 6),
        p90_curtailment_mw=round(curtailment.p90_mw, 6),
        violation_hours=curtailment.expected_hours,
        main_recurring_constraint=main_constraint,
    )


def _dominant_string(values: tuple[str, ...]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _envelope_record_row(record: QstsEnvelopeRecord) -> dict[str, object]:
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


def _envelope_summary_row(row: QstsEnvelopeSummaryRow) -> dict[str, object]:
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


def _contractual_envelope_row(row: ContractualEnvelopeRow) -> dict[str, object]:
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


def _render_baseline_table(buses: tuple[QstsBusResult, ...]) -> str:
    lines = [
        "| bus_id | baseline_violating_hours | dominant_pre_existing_constraint | max_voltage_pu | max_loading_percent |",
        "| ---: | ---: | --- | ---: | ---: |",
    ]
    for bus in buses:
        lines.append(
            "| "
            f"{bus.bus_id} | {bus.baseline_violating_hours} | "
            f"{bus.baseline_main_constraint or '-'} | "
            f"{_format_optional_float(bus.baseline_max_vm_pu)} | "
            f"{_format_optional_float(bus.baseline_max_loading_percent)} |"
        )
    return "\n".join(lines)


def _render_investor_decision_table(buses: tuple[QstsBusResult, ...]) -> str:
    lines = [
        "| rank | bus_id | qsts_verdict | static_firm_mw | static_conditional_mw | qsts_p90_mw | qsts_mwh | main_constraint |",
        "| ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for bus in buses:
        lines.append(
            "| "
            f"{bus.rank} | {bus.bus_id} | {bus.qsts_verdict} | "
            f"{bus.static_firm_capacity_mw:.3f} | "
            f"{bus.static_conditional_capacity_mw:.3f} | "
            f"{bus.curtailment.p90_mw:.3f} | "
            f"{bus.curtailment.expected_mwh:.3f} | "
            f"{bus.main_recurring_constraint or '-'} |"
        )
    return "\n".join(lines)


def _qsts_economics_proxy(result: QstsResult) -> QstsEconomicsProxy:
    if not result.buses:
        curtailed_mwh = 0.0
    else:
        curtailed_mwh = result.buses[0].curtailment.expected_mwh
    requested_kw = result.request.requested_mw * 1000.0
    energy_capacity_mwh = result.request.requested_mw * result.request.storage_duration_hours
    capex = requested_kw * result.request.capex_eur_per_kw
    annual_gross_revenue = (
        result.request.requested_mw * result.request.gross_revenue_eur_per_mw_year
    )
    annual_curtailment_loss = curtailed_mwh * result.request.curtailment_penalty_eur_per_mwh
    annual_fixed_opex = requested_kw * result.request.fixed_opex_eur_per_kw_year
    annual_ebitda = annual_gross_revenue - annual_curtailment_loss - annual_fixed_opex
    connect_now_value = _discounted_annuity(
        annual_ebitda,
        years=result.request.reinforcement_wait_years,
        discount_rate=result.request.discount_rate,
    )
    wait_value = _discounted_annuity(
        annual_gross_revenue - annual_fixed_opex,
        years=result.request.reinforcement_wait_years,
        discount_rate=result.request.discount_rate,
    )
    return QstsEconomicsProxy(
        storage_duration_hours=round(result.request.storage_duration_hours, 6),
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


def _render_qsts_investment_table(
    buses: tuple[QstsBusResult, ...],
    contractual_rows: tuple[ContractualEnvelopeRow, ...],
) -> str:
    contract_ranges = _contractual_p10_ranges(contractual_rows)
    lines = [
        "| rank | bus_id | verdict | firm_mw | conditional_mw | contract_p10_min_mw | contract_p10_max_mw | qsts_p90_mw | qsts_mwh | dominant_constraint |",
        "| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for bus in buses:
        contract_min, contract_max = contract_ranges.get(bus.bus_id, (None, None))
        lines.append(
            "| "
            f"{bus.rank} | {bus.bus_id} | {bus.qsts_verdict} | "
            f"{bus.static_firm_capacity_mw:.3f} | "
            f"{bus.static_conditional_capacity_mw:.3f} | "
            f"{_format_optional_float(contract_min)} | "
            f"{_format_optional_float(contract_max)} | "
            f"{bus.curtailment.p90_mw:.3f} | "
            f"{bus.curtailment.expected_mwh:.3f} | "
            f"{bus.main_recurring_constraint or '-'} |"
        )
    return "\n".join(lines)


def _render_contractual_summary_table(rows: tuple[ContractualEnvelopeRow, ...]) -> str:
    if not rows:
        return "No contractual envelope rows available."
    by_bus_direction: dict[tuple[int, str, Direction], list[ContractualEnvelopeRow]] = {}
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
            f"{_dominant_string(tuple(row.dominant_incremental_constraint for row in group)) or '-'} |"
        )
    return "\n".join(lines)


def _render_contractual_envelope_table(rows: tuple[ContractualEnvelopeRow, ...]) -> str:
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


def _contractual_p10_ranges(
    rows: tuple[ContractualEnvelopeRow, ...],
) -> dict[int, tuple[float, float]]:
    values_by_bus: dict[int, list[float]] = {}
    for row in rows:
        values_by_bus.setdefault(row.bus_id, []).append(row.allowed_mw_p10)
    return {
        bus_id: (min(values), max(values))
        for bus_id, values in values_by_bus.items()
        if values
    }


def _static_vs_qsts_comparison_rows(
    result: QstsResult,
    contractual_rows: tuple[ContractualEnvelopeRow, ...],
) -> tuple[dict[str, object], ...]:
    by_bus: dict[int, list[ContractualEnvelopeRow]] = {}
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
                "contractual_allowed_mw_p10_min": _format_contract_min(
                    [row.allowed_mw_p10 for row in contract]
                ),
                "contractual_allowed_mw_p25_min": _format_contract_min(
                    [row.allowed_mw_p25 for row in contract]
                ),
                "contractual_allowed_mw_p50_min": _format_contract_min(
                    [row.allowed_mw_p50 for row in contract]
                ),
                "contractual_allowed_mw_min": _format_contract_min(
                    [row.allowed_mw_min for row in contract]
                ),
                "qsts_p90_curtailment_mw": f"{bus.curtailment.p90_mw:.6f}",
                "qsts_expected_curtailment_mwh": f"{bus.curtailment.expected_mwh:.6f}",
                "main_recurring_constraint": bus.main_recurring_constraint,
                "runtime_seconds": f"{result.performance.runtime_seconds:.6f}",
            }
        )
    return tuple(rows)


def _format_contract_min(values: list[float]) -> str:
    if not values:
        return ""
    return f"{min(values):.6f}"


def _render_envelope_comparison_table(comparisons: tuple[QstsEnvelopeComparison, ...]) -> str:
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


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}"


def _max_optional(current: float | None, candidate: float | None) -> float | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return max(current, candidate)


def _result_min(net: object, table_name: str, column: str) -> float | None:
    table = getattr(net, table_name, None)
    if table is None or column not in table or table.empty:
        return None
    return round(float(table[column].min()), 6)


def _result_max(net: object, table_name: str, column: str) -> float | None:
    table = getattr(net, table_name, None)
    if table is None or column not in table or table.empty:
        return None
    return round(float(table[column].max()), 6)


def _max_loading_percent(net: object) -> float | None:
    values: list[float] = []
    for table_name in ("res_line", "res_trafo", "res_trafo3w"):
        value = _result_max(net, table_name, "loading_percent")
        if value is not None:
            values.append(value)
    if not values:
        return None
    return round(max(values), 6)


def _is_worse(metric: str, candidate_value: float, baseline_value: float, tolerance: float) -> bool:
    if metric.endswith(".min"):
        return candidate_value < baseline_value - tolerance
    return candidate_value > baseline_value + tolerance


def _qsts_verdict(
    curtailment: CurtailmentEstimate,
    p90_tolerance_mw: float,
    mwh_tolerance: float,
) -> str:
    if curtailment.p90_mw <= 1e-9 and curtailment.expected_mwh <= 1e-9:
        return "go"
    if (
        curtailment.p90_mw <= p90_tolerance_mw + 1e-9
        and curtailment.expected_mwh <= mwh_tolerance + 1e-9
    ):
        return "go-with-conditions"
    return "no-go"


def _write_run_manifest(
    result: QstsResult,
    output_dir: Path,
    output_paths: dict[str, object],
    manifest_path: Path,
    command: Sequence[str] | None,
) -> None:
    manifest = {
        "schema_version": "qsts-run-manifest-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "command": list(command) if command is not None else None,
        "request": _json_ready(asdict(result.request)),
        "constraint_settings": _json_ready(asdict(result.settings)),
        "source": result.source,
        "outputs": _manifest_outputs(output_dir, output_paths),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "thesegrid_version": _package_version(),
        },
        "git": _git_metadata(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest_outputs(output_dir: Path, output_paths: dict[str, object]) -> dict[str, object]:
    outputs: dict[str, object] = {}
    for key, value in output_paths.items():
        if isinstance(value, Path):
            outputs[key] = _relative_or_string(value, output_dir)
        elif isinstance(value, list):
            outputs[key] = [
                _relative_or_string(path, output_dir) if isinstance(path, Path) else str(path)
                for path in value
            ]
        else:
            outputs[key] = str(value)
    return outputs


def _relative_or_string(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _json_ready(value: object) -> object:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _package_version() -> str:
    try:
        return version("thesegrid")
    except PackageNotFoundError:
        return "editable"


def _git_metadata() -> dict[str, object]:
    return {
        "commit": _git_output("rev-parse", "HEAD"),
        "branch": _git_output("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": _git_dirty(),
    }


def _git_output(*args: str) -> str | None:
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


def _git_dirty() -> bool | None:
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


def _main_recurring_constraint(counts: dict[str, int]) -> str:
    if not counts:
        return ""
    constraint, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return f"{constraint}: count={count}"


def _bus_result_row(bus: QstsBusResult) -> dict[str, object]:
    return {
        "rank": bus.rank,
        "bus_id": bus.bus_id,
        "bus_name": bus.bus_name,
        "qsts_verdict": bus.qsts_verdict,
        "requested_mw": f"{bus.requested_mw:.6f}",
        "static_firm_capacity_mw": f"{bus.static_firm_capacity_mw:.6f}",
        "static_conditional_capacity_mw": f"{bus.static_conditional_capacity_mw:.6f}",
        "baseline_mode": "incremental",
        "p90_curtailment_tolerance_mw": f"{bus.p90_curtailment_tolerance_mw:.6f}",
        "feasible_hours": bus.feasible_hours,
        "violation_hours": bus.violation_hours,
        "expected_curtailment_mwh": f"{bus.curtailment.expected_mwh:.6f}",
        "p50_curtailment_mw": f"{bus.curtailment.p50_mw:.6f}",
        "p90_curtailment_mw": f"{bus.curtailment.p90_mw:.6f}",
        "main_recurring_constraint": bus.main_recurring_constraint,
    }


def _investor_decision_row(bus: QstsBusResult) -> dict[str, object]:
    return {
        "rank": bus.rank,
        "bus_id": bus.bus_id,
        "bus_name": bus.bus_name,
        "qsts_verdict": bus.qsts_verdict,
        "static_firm_capacity_mw": f"{bus.static_firm_capacity_mw:.6f}",
        "static_conditional_capacity_mw": f"{bus.static_conditional_capacity_mw:.6f}",
        "qsts_p90_curtailment_mw": f"{bus.curtailment.p90_mw:.6f}",
        "qsts_expected_curtailment_mwh": f"{bus.curtailment.expected_mwh:.6f}",
        "main_recurring_constraint": bus.main_recurring_constraint,
    }


def _render_qsts_table(buses: tuple[QstsBusResult, ...]) -> str:
    lines = [
        "| rank | bus_id | bus_name | qsts_verdict | static_firm_mw | static_conditional_mw | qsts_p90_mw | qsts_mwh |",
        "| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for bus in buses:
        lines.append(
            "| "
            f"{bus.rank} | {bus.bus_id} | {bus.bus_name} | {bus.qsts_verdict} | "
            f"{bus.static_firm_capacity_mw:.3f} | {bus.static_conditional_capacity_mw:.3f} | "
            f"{bus.curtailment.p90_mw:.3f} | {bus.curtailment.expected_mwh:.3f} |"
        )
    return "\n".join(lines)
