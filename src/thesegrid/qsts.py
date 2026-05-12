from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from thesegrid.capacity import evaluate_dispatch, find_max_feasible
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
    "allowed_mw_p50",
    "allowed_mw_min",
    "curtailed_mw_p90",
    "dominant_incremental_constraint",
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
    p90_curtailment_tolerance_mw: float = 0.0
    expected_curtailment_tolerance_mwh: float = 0.0

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
        if self.p90_curtailment_tolerance_mw < 0:
            raise ValueError("p90_curtailment_tolerance_mw must be non-negative")
        if self.expected_curtailment_tolerance_mwh < 0:
            raise ValueError("expected_curtailment_tolerance_mwh must be non-negative")


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
class QstsResult:
    request: QstsRequest
    buses: tuple[QstsBusResult, ...]
    source: str = "actual hourly power-flow validation"
    settings: ConstraintSettings = field(default_factory=ConstraintSettings)


@dataclass(frozen=True)
class QstsOutputPaths:
    results_csv_path: Path
    summary_path: Path
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
    bus_results = tuple(
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
        )
        for selected in selected_buses
    )
    return QstsResult(request=request, buses=bus_results, settings=settings)


def write_qsts_outputs(result: QstsResult, output_dir: Path) -> QstsOutputPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    results_csv = output_dir / "qsts_results.csv"
    summary_path = output_dir / "qsts_summary.md"
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

    summary_path.write_text(render_qsts_summary(result), encoding="utf-8")
    return QstsOutputPaths(
        results_csv_path=results_csv,
        summary_path=summary_path,
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
) -> QstsBusResult:
    records: list[QstsHourlyRecord] = []
    constraint_counts: dict[str, int] = {}
    baseline_constraint_counts: dict[str, int] = {}
    baseline_violating_hours = 0
    baseline_max_vm_pu: float | None = None
    baseline_max_loading_percent: float | None = None
    timestamps = _timestamps_for_steps(time_steps)
    baseline_cache = baseline_cache if baseline_cache is not None else {}

    for position, time_step in enumerate(time_steps):
        _apply_profiles(net, profiles, time_step)
        if time_step not in baseline_cache:
            baseline_cache[time_step] = _baseline_state(net, selected.bus_id, settings)
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
                net,
                selected.bus_id,
                direction,
                requested_mw,
                settings,
                baseline,
            )
            if requested.incrementally_feasible:
                feasible_mw = requested_mw
                incremental_violations = requested.incremental_violations
            else:
                feasible_mw = find_max_feasible(
                    upper_mw=requested_mw,
                    is_feasible=lambda mw, direction=direction: _evaluate_incremental_dispatch(
                        net,
                        selected.bus_id,
                        direction,
                        mw,
                        settings,
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


def _baseline_state(
    net: object,
    bus_id: int,
    settings: ConstraintSettings,
) -> _BaselineState:
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
    net: object,
    bus_id: int,
    direction: Direction,
    mw: float,
    settings: ConstraintSettings,
    baseline: dict[tuple[str, int, str], float],
) -> _IncrementalDispatchEvaluation:
    evaluation = evaluate_dispatch(net, bus_id, direction, mw, settings)
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


def _render_contractual_envelope_table(rows: tuple[ContractualEnvelopeRow, ...]) -> str:
    if not rows:
        return "No contractual envelope rows available."
    lines = [
        "| bus_id | direction | season | time_block | allowed_mw_p10 | allowed_mw_p50 | allowed_mw_min | curtailed_mw_p90 | dominant_constraint |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row.bus_id} | {row.direction} | {row.season} | {row.time_block} | "
            f"{row.allowed_mw_p10:.3f} | "
            f"{row.allowed_mw_p50:.3f} | "
            f"{row.allowed_mw_min:.3f} | "
            f"{row.curtailed_mw_p90:.3f} | "
            f"{row.dominant_incremental_constraint or '-'} |"
        )
    return "\n".join(lines)


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
