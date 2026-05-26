from __future__ import annotations

import csv
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
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
from thesegrid.decision_frontier import decision_frontier_rows
from thesegrid.gabarits import GabaritKind, annual_timestamps, is_restricted
from thesegrid.models import ConstraintViolation, CurtailmentEstimate, Direction
from thesegrid.networks import ToyNetwork, load_network
from thesegrid.risk import estimate_curtailment


QSTS_RESULT_COLUMNS = (
    "rank",
    "bus_id",
    "bus_name",
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


@dataclass(frozen=True)
class QstsRequest:
    network_code: str
    screening_csv: Path
    requested_mw: float
    top_n: int = 10
    bus_ids: tuple[int, ...] = ()
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
    pf_numba: bool = False
    pf_algorithm: str = "nr"
    pf_init: str = "auto"
    pf_recycle: bool = False

    def __post_init__(self) -> None:
        if not self.network_code:
            raise ValueError("network_code must not be empty")
        if self.network_code == "toy":
            raise ValueError("QSTS requires a SimBench network; 'toy' is only for smoke tests")
        if self.requested_mw <= 0:
            raise ValueError("requested_mw must be positive")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")
        if any(bus_id < 0 for bus_id in self.bus_ids):
            raise ValueError("bus_ids must be non-negative")
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
        if self.pf_algorithm not in {"nr", "iwamoto_nr", "bfsw", "gs", "fdbx", "fdxb"}:
            raise ValueError("pf_algorithm must be a supported pandapower runpp algorithm")
        if self.pf_init not in {"auto", "flat", "dc", "results"}:
            raise ValueError("pf_init must be one of auto, flat, dc, or results")


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
    sampled_curtailment_mwh: float = 0.0
    weighted_curtailment_mwh: float = 0.0
    curtailment_energy_ratio: float = 0.0
    baseline_violating_hours: int = 0
    baseline_main_constraint: str = ""
    baseline_max_vm_pu: float | None = None
    baseline_max_loading_percent: float | None = None

    def __post_init__(self) -> None:
        if self.sampled_curtailment_mwh == 0.0 and self.curtailment.expected_mwh > 0.0:
            object.__setattr__(self, "sampled_curtailment_mwh", self.curtailment.expected_mwh)
        if self.weighted_curtailment_mwh == 0.0 and self.curtailment.expected_mwh > 0.0:
            object.__setattr__(self, "weighted_curtailment_mwh", self.curtailment.expected_mwh)
        if self.curtailment_energy_ratio == 0.0 and self.weighted_curtailment_mwh > 0.0:
            object.__setattr__(
                self,
                "curtailment_energy_ratio",
                _curtailment_energy_ratio(self.weighted_curtailment_mwh, self.requested_mw),
            )


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
class QstsRiskSummaryRow:
    bus_id: int
    bus_name: str
    qsts_verdict: str
    curtailment_hours: int
    expected_curtailment_mwh: float
    sampled_curtailment_mwh: float
    weighted_curtailment_mwh: float
    curtailment_energy_ratio: float
    curtailment_p90_mw: float
    curtailment_p95_mw: float
    curtailment_p99_mw: float
    curtailment_max_mw: float
    max_event_hours: int
    max_event_mwh: float
    dominant_constraint: str
    verdict_driver: str
    tail_risk_flag: bool


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
    evaluated_bus_hours: int = 0
    power_flow_calls_per_bus_hour: float = 0.0
    runtime_seconds_per_bus_hour: float = 0.0
    parallelization_unit: str = "bus"


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
    risk_summary_csv_path: Path
    risk_summary_json_path: Path
    economics_csv_path: Path
    decision_frontier_csv_path: Path
    bus_detail_paths: tuple[Path, ...]


def select_top_buses_from_screening_csv(
    csv_path: Path,
    top_n: int,
    bus_ids: tuple[int, ...] = (),
) -> tuple[QstsSelectedBus, ...]:
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = sorted(csv.DictReader(handle), key=lambda row: int(row["rank"]))
    if bus_ids:
        by_bus_id = {int(row["bus_id"]): row for row in rows}
        missing = [bus_id for bus_id in bus_ids if bus_id not in by_bus_id]
        if missing:
            missing_text = ", ".join(str(bus_id) for bus_id in missing)
            raise ValueError(f"bus_ids not found in screening_csv: {missing_text}")
        rows = [by_bus_id[bus_id] for bus_id in bus_ids]
    else:
        rows = rows[:top_n]
    selected: list[QstsSelectedBus] = []
    for row in rows:
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


def weighted_qsts_curtailment_estimate(
    hourly_records: pd.DataFrame,
    timestamp_weights: dict[str, float],
) -> CurtailmentEstimate:
    if hourly_records.empty:
        return estimate_curtailment(())
    worst_by_timestamp = hourly_records.groupby("timestamp")["curtailed_mw"].max()
    weighted_mwh = 0.0
    for timestamp, curtailed_mw in worst_by_timestamp.items():
        weighted_mwh += max(0.0, float(curtailed_mw)) * timestamp_weights.get(str(timestamp), 1.0)
    base = estimate_curtailment(worst_by_timestamp.tolist())
    return CurtailmentEstimate(
        expected_hours=base.expected_hours,
        expected_mwh=round(weighted_mwh, 6),
        p50_mw=base.p50_mw,
        p90_mw=base.p90_mw,
    )


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
    selected_buses = select_top_buses_from_screening_csv(
        request.screening_csv,
        request.top_n,
        bus_ids=request.bus_ids,
    )
    time_steps = _profile_time_steps(
        profiles,
        start_hour=request.start_hour,
        duration_hours=request.duration_hours,
        sample_every_n_hours=request.sample_every_n_hours,
        stratified_sample=request.stratified_sample,
    )
    if not time_steps:
        raise ValueError("QSTS requires at least one profile time step")
    timestamp_weights = _timestamp_weights(
        time_steps,
        _time_step_weights(time_steps, request, _available_profile_hours(profiles)),
    )

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
                timestamp_weights=timestamp_weights,
                request=request,
                baseline_cache=baseline_cache,
                tracker=tracker,
            )
        )
    tracker.evaluated_time_steps = len(time_steps)
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
    risk_summary_csv = output_dir / "qsts_risk_summary.csv"
    risk_summary_json = output_dir / "qsts_risk_summary.json"
    economics_csv = output_dir / "qsts_economics.csv"
    decision_frontier_csv = output_dir / "decision_frontier.csv"
    envelope_csv = output_dir / "qsts_envelope.csv"
    envelope_summary_csv = output_dir / "qsts_envelope_summary.csv"
    contractual_envelope_csv = output_dir / "contractual_envelope.csv"
    detail_paths: list[Path] = []

    with results_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QSTS_RESULT_COLUMNS)
        writer.writeheader()
        for bus in result.buses:
            writer.writerow(
                _bus_result_row(
                    bus,
                    result.request,
                    evaluated_time_steps=result.performance.evaluated_time_steps,
                )
            )

    with investor_decision_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVESTOR_DECISION_COLUMNS)
        writer.writeheader()
        for bus in result.buses:
            writer.writerow(
                _investor_decision_row(
                    bus,
                    result.request,
                    evaluated_time_steps=result.performance.evaluated_time_steps,
                )
            )

    with economics_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QSTS_ECONOMICS_COLUMNS)
        writer.writeheader()
        for bus in result.buses:
            writer.writerow(_qsts_economics_row(result.request, bus))

    with decision_frontier_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "bus_id",
                "bus_name",
                "policy",
                "qsts_p90_mw",
                "p90_curtailment_ratio",
                "weighted_curtailment_mwh",
                "curtailment_energy_ratio",
                "max_event_hours",
                "max_event_mwh",
                "max_event_mwh_per_mw",
                "policy_max_p90_ratio",
                "policy_max_energy_ratio",
                "policy_max_event_hours",
                "policy_max_event_mwh_per_mw",
                "frontier_verdict",
                "validation_level",
            ),
        )
        writer.writeheader()
        for bus in result.buses:
            max_event_hours, max_event_mwh = _bus_max_curtailment_event(bus)
            for row in decision_frontier_rows(
                bus_id=bus.bus_id,
                bus_name=bus.bus_name,
                requested_mw=bus.requested_mw,
                qsts_p90_mw=bus.curtailment.p90_mw,
                weighted_curtailment_mwh=bus.weighted_curtailment_mwh,
                curtailment_energy_ratio=bus.curtailment_energy_ratio,
                max_event_hours=max_event_hours,
                max_event_mwh=max_event_mwh,
                validation_level=_validation_level(
                    result.request,
                    result.performance.evaluated_time_steps,
                ),
            ):
                writer.writerow(_decision_frontier_row(row))

    risk_summary_rows = summarize_qsts_risk(result)
    with risk_summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QSTS_RISK_SUMMARY_COLUMNS)
        writer.writeheader()
        for row in risk_summary_rows:
            writer.writerow(_risk_summary_row(row))
    risk_summary_json.write_text(
        json.dumps(
            [_json_ready(asdict(row)) for row in risk_summary_rows],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

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
            "qsts_risk_summary": risk_summary_csv,
            "qsts_risk_summary_json": risk_summary_json,
            "qsts_economics": economics_csv,
            "decision_frontier": decision_frontier_csv,
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
        risk_summary_csv_path=risk_summary_csv,
        risk_summary_json_path=risk_summary_json,
        economics_csv_path=economics_csv,
        decision_frontier_csv_path=decision_frontier_csv,
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


def summarize_qsts_risk(result: QstsResult) -> tuple[QstsRiskSummaryRow, ...]:
    rows: list[QstsRiskSummaryRow] = []
    for bus in result.buses:
        frame = pd.DataFrame(asdict(record) for record in bus.hourly_records)
        if frame.empty:
            curtailed = pd.Series(dtype=float)
            dominant_constraint = ""
        else:
            frame["curtailed_mw"] = frame["curtailed_mw"].astype(float).clip(lower=0.0)
            worst_index = frame.groupby("timestamp")["curtailed_mw"].idxmax()
            worst_by_timestamp = frame.loc[worst_index].sort_values("timestamp")
            curtailed = worst_by_timestamp["curtailed_mw"].reset_index(drop=True)
            constraint_counts: dict[str, int] = {}
            for constraint in frame.loc[
                frame["curtailed_mw"] > 1e-9,
                "incremental_binding_constraint",
            ]:
                if constraint:
                    constraint_counts[constraint] = constraint_counts.get(constraint, 0) + 1
            dominant_constraint = _main_recurring_constraint(constraint_counts)
        max_event_hours, max_event_mwh = _max_curtailment_event(frame)
        verdict_driver = _qsts_verdict_driver(
            bus.curtailment,
            p90_tolerance_mw=result.request.p90_curtailment_tolerance_mw,
            mwh_tolerance=result.request.expected_curtailment_tolerance_mwh,
        )
        rows.append(
            QstsRiskSummaryRow(
                bus_id=bus.bus_id,
                bus_name=bus.bus_name,
                qsts_verdict=bus.qsts_verdict,
                curtailment_hours=int((curtailed > 1e-9).sum()) if not curtailed.empty else 0,
                expected_curtailment_mwh=bus.curtailment.expected_mwh,
                sampled_curtailment_mwh=bus.sampled_curtailment_mwh,
                weighted_curtailment_mwh=bus.weighted_curtailment_mwh,
                curtailment_energy_ratio=bus.curtailment_energy_ratio,
                curtailment_p90_mw=_series_quantile(curtailed, 0.90),
                curtailment_p95_mw=_series_quantile(curtailed, 0.95),
                curtailment_p99_mw=_series_quantile(curtailed, 0.99),
                curtailment_max_mw=round(float(curtailed.max()), 6)
                if not curtailed.empty
                else 0.0,
                max_event_hours=max_event_hours,
                max_event_mwh=max_event_mwh,
                dominant_constraint=dominant_constraint,
                verdict_driver=verdict_driver,
                tail_risk_flag=(
                    bus.curtailment.p90_mw
                    <= result.request.p90_curtailment_tolerance_mw + 1e-9
                    and bus.curtailment.expected_mwh
                    > result.request.expected_curtailment_tolerance_mwh + 1e-9
                ),
            )
        )
    return tuple(rows)


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
        risk_table = "No QSTS risk rows available."
        comparison_table = "No envelope comparison available."
        contractual_table = "No contractual envelope available."
        recommended_next_action = "not_applicable"
    else:
        top_table = _render_qsts_table(
            result.buses,
            result.request,
            evaluated_time_steps=result.performance.evaluated_time_steps,
        )
        investor_table = _render_investor_decision_table(
            result.buses,
            result.request,
            evaluated_time_steps=result.performance.evaluated_time_steps,
        )
        baseline_table = _render_baseline_table(result.buses)
        risk_table = _render_risk_summary_table(summarize_qsts_risk(result))
        comparison_table = _render_envelope_comparison_table(compare_qsts_envelopes(result))
        contractual_table = _render_contractual_envelope_table(
            synthesize_contractual_envelope(qsts_envelope_records(result)).rows
        )
        primary_risk = summarize_qsts_risk(result)[0]
        recommended_next_action = _recommended_next_action(
            result.buses[0].qsts_verdict,
            primary_risk.verdict_driver,
            result.request,
            result.performance.evaluated_time_steps,
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
- validation_level: {_validation_level(result.request, result.performance.evaluated_time_steps)}
- decision_confidence: {_decision_confidence(result.request, result.performance.evaluated_time_steps)}
- recommended_next_action: {recommended_next_action}

## Results

{top_table}

## Investor Decision Table

{investor_table}

## Baseline Summary

{baseline_table}

## Risk Summary

{risk_table}

## Envelope Comparison

{comparison_table}

## Contractual Envelope

{contractual_table}

## Interpretation

- QSTS results replay time-varying network operating points before checking BESS injection and withdrawal.
- QSTS-derived envelope rows are extracted from the hourly feasible MW already computed by QSTS; no extra power-flow pass is hidden in the export step.
- Validation levels are progressive: screening_only is triage, qsts_short is smoke validation, qsts_stratified is pre-demo evidence, and qsts_full_year is the MVP investor reference.
- Contractual envelope rows summarize QSTS-derived allowed MW into RTE-inspired V1 seasons and time blocks using P10 allowed MW as the recommended conservative value.
- Risk summary rows expose tail events where P90 can hide rare curtailed energy.
- Verdicts are baseline-aware: pre-existing network violations are separated from new or worsened candidate violations.
- Static proxy curtailment and QSTS curtailment are not equivalent; QSTS is the higher-evidence validation layer.
- The study still excludes short-circuit, protection, dynamic stability, N-1 security, harmonics, and official operator planning criteria.
"""


def render_qsts_investment_memo(result: QstsResult) -> str:
    if not result.buses:
        primary = "No candidate bus was selected for QSTS validation."
        decision_snapshot = "No QSTS decision rows available."
        investor_table = "No investor decision rows available."
        contractual_summary = "No contractual envelope rows available."
        contractual_detail = "No contractual envelope rows available."
        decision_drivers = "No QSTS decision drivers available."
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
        decision_drivers = _render_decision_drivers(summarize_qsts_risk(result))
        decision_snapshot = _render_decision_snapshot(result)
    economics = _qsts_economics_proxy(result)
    economics_table = _render_qsts_economics_table(result)
    return f"""# QSTS BESS Investment Memo

This memo is an early-stage buyer-side decision aid for BESS flexible connection pre-feasibility. It does not replace an official grid-connection study.

Cette enveloppe est une approximation pré-faisabilité inspirée du cadre RTE/CRE ; elle ne constitue pas une PTF ni une offre officielle RTE/Enedis.

## Primary Recommendation

{primary}

## Decision Snapshot

{decision_snapshot}

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

## Three-Site Comparison

{investor_table}

## Decision Drivers

{decision_drivers}

## Contractual Envelope Summary

{contractual_summary}

## Contractual Envelope Detail

{contractual_detail}

## Primary Bus Economics Proxy

This is a proxy, not bankable revenue modelling. It is intended to compare connect-now
under a flexible gabarit against waiting for reinforcement; it is not a PTF, an
official offer, or a financing model.

- storage_duration_hours: {economics.storage_duration_hours:.3f}
- reinforcement_wait_years: {economics.reinforcement_wait_years:.3f}
- discount_rate: {economics.discount_rate:.3f}
- energy_capacity_mwh: {economics.energy_capacity_mwh:.3f}
- capex_eur: {economics.capex_eur:.2f}
- annual_gross_revenue_eur: {economics.annual_gross_revenue_eur:.2f}
- annual_curtailment_loss_eur: {economics.annual_curtailment_loss_eur:.2f}
- annual_fixed_opex_eur: {economics.annual_fixed_opex_eur:.2f}
- annual_ebitda_proxy_eur: {economics.annual_ebitda_proxy_eur:.2f}
- connect_now_value_eur: {economics.connect_now_value_eur:.2f}
- wait_value_eur: {economics.wait_value_eur:.2f}
- delta_npv_eur: {economics.delta_npv_eur:.2f}

## Per-Bus Economics Proxy

{economics_table}

## Interpretation

- Static screening is a proxy ranking layer; QSTS is the hourly power-flow validation layer.
- The contractual envelope is synthesized from QSTS allowed MW by direction, V1 season, and fixed time block.
- `contract_p10_min_mw` is the tightest conservative contractual MW across the synthesized blocks for a bus.
- Tail-risk diagnostics explain cases where P90 MW is acceptable but MWh risk rare but energetically material.
- Remaining exclusions: short-circuit, protection, dynamic stability, N-1 security, harmonics, and official operator planning criteria.
"""


def render_annual_validation_summary(result: QstsResult) -> str:
    risk_table = _render_risk_summary_table(summarize_qsts_risk(result))
    return f"""# Annual Validation Summary

This file summarizes the QSTS validation bundle. It can be used for full-year or sampled annual campaigns; check `run_manifest.json` for the exact sampling mode and duration.

## Validation Level

- validation_level: {_validation_level(result.request, result.performance.evaluated_time_steps)}
- decision_confidence: {_decision_confidence(result.request, result.performance.evaluated_time_steps)}
- policy: screening_only -> qsts_short -> qsts_stratified -> qsts_full_year
- investor_reference: qsts_full_year

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
- qsts_risk_summary.csv
- contractual_envelope.csv
- qsts_results.csv
- run_manifest.json

## Risk Summary

{risk_table}
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
    timestamp_weights: dict[str, float] | None = None,
    request: QstsRequest | None = None,
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

    with _QstsDispatchEvaluator(net, selected.bus_id, settings, tracker, request=request) as evaluator:
        for position, time_step in enumerate(time_steps):
            _apply_profiles(net, profiles, time_step)
            evaluator.reset_candidate()
            if time_step not in baseline_cache:
                tracker.baseline_cache_misses += 1
                baseline_cache[time_step] = _cached_baseline_state(
                    net,
                    selected.bus_id,
                    settings,
                    tracker,
                    request=request,
                )
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
    sampled_curtailment = qsts_curtailment_estimate(hourly_frame)
    curtailment = weighted_qsts_curtailment_estimate(hourly_frame, timestamp_weights or {})
    total_hours = len(time_steps)
    feasible_hours = total_hours - curtailment.expected_hours
    energy_ratio = _curtailment_energy_ratio(curtailment.expected_mwh, requested_mw)
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
        sampled_curtailment_mwh=sampled_curtailment.expected_mwh,
        weighted_curtailment_mwh=curtailment.expected_mwh,
        curtailment_energy_ratio=energy_ratio,
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


def _available_profile_hours(profiles: dict[str, pd.DataFrame]) -> int:
    lengths = [len(frame) for frame in profiles.values() if not frame.empty]
    return min(lengths) if lengths else 0


def _time_step_weights(
    time_steps: tuple[int, ...],
    request: QstsRequest,
    available_hours: int,
) -> dict[int, float]:
    if not time_steps:
        return {}
    if not request.stratified_sample:
        return {time_step: 1.0 for time_step in time_steps}

    timestamps = annual_timestamps(2026)
    upper = min(available_hours, len(timestamps))
    if upper < 8760:
        return {time_step: 1.0 for time_step in time_steps}

    return {
        time_step: float(_days_in_month(timestamps[time_step].month) * _time_block_width(timestamps[time_step].hour))
        for time_step in time_steps
        if 0 <= time_step < len(timestamps)
    }


def _timestamp_weights(
    time_steps: tuple[int, ...],
    time_step_weights: dict[int, float],
) -> dict[str, float]:
    timestamps = _timestamps_for_steps(time_steps)
    return {
        str(timestamp): time_step_weights.get(time_step, 1.0)
        for time_step, timestamp in zip(time_steps, timestamps, strict=True)
    }


def _days_in_month(month: int) -> int:
    month_lengths = {
        1: 31,
        2: 28,
        3: 31,
        4: 30,
        5: 31,
        6: 30,
        7: 31,
        8: 31,
        9: 30,
        10: 31,
        11: 30,
        12: 31,
    }
    return month_lengths[month]


def _time_block_width(hour: int) -> int:
    blocks = (
        (0, 7),
        (7, 10),
        (10, 13),
        (13, 17),
        (17, 18),
        (18, 21),
        (21, 24),
    )
    for start, end in blocks:
        if start <= hour < end:
            return end - start
    return 1


def _curtailment_energy_ratio(weighted_curtailment_mwh: float, requested_mw: float) -> float:
    denominator = requested_mw * 8760.0
    if denominator <= 0:
        return 0.0
    return round(weighted_curtailment_mwh / denominator, 6)


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
        self.evaluated_bus_hours = 0
        self.evaluated_buses = 0

    def record_baseline_power_flow(self) -> None:
        self.power_flow_calls += 1
        self.baseline_power_flow_calls += 1

    def record_candidate_power_flow(self) -> None:
        self.power_flow_calls += 1
        self.candidate_power_flow_calls += 1

    def record_time_step(self) -> None:
        self.evaluated_bus_hours += 1
        if (
            self.progress_every_n_hours > 0
            and self.evaluated_bus_hours % self.progress_every_n_hours == 0
        ):
            total = self.total_buses * self.total_time_steps
            print(
                f"qsts progress: {self.evaluated_bus_hours}/{total} bus-hours evaluated",
                file=sys.stderr,
            )

    def to_stats(self, runtime_seconds: float) -> QstsPerformanceStats:
        evaluated_bus_hours = self.evaluated_bus_hours
        power_flow_calls_per_bus_hour = (
            self.power_flow_calls / evaluated_bus_hours if evaluated_bus_hours else 0.0
        )
        runtime_seconds_per_bus_hour = runtime_seconds / evaluated_bus_hours if evaluated_bus_hours else 0.0
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
            evaluated_bus_hours=evaluated_bus_hours,
            power_flow_calls_per_bus_hour=round(power_flow_calls_per_bus_hour, 6),
            runtime_seconds_per_bus_hour=round(runtime_seconds_per_bus_hour, 6),
            parallelization_unit="bus",
        )


class _QstsDispatchEvaluator:
    def __init__(
        self,
        net: object,
        bus_id: int,
        settings: ConstraintSettings,
        tracker: _QstsPerformanceTracker,
        request: QstsRequest | None = None,
    ) -> None:
        self.net = net
        self.bus_id = bus_id
        self.settings = settings
        self.tracker = tracker
        self.request = request
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

        self.reset_candidate()
        if direction == "injection" and self._sgen_id is not None:
            self.net.sgen.at[self._sgen_id, "p_mw"] = mw
        elif direction == "withdrawal" and self._load_id is not None:
            self.net.load.at[self._load_id, "p_mw"] = mw
        try:
            _run_pandapower_power_flow(self.net, self.request)
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
    request: QstsRequest | None = None,
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

    try:
        _run_pandapower_power_flow(net, request)
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


def _cached_baseline_state(
    net: object,
    bus_id: int,
    settings: ConstraintSettings,
    tracker: _QstsPerformanceTracker,
    request: QstsRequest | None,
) -> _BaselineState:
    try:
        return _baseline_state(net, bus_id, settings, tracker, request=request)
    except TypeError as exc:
        if "unexpected keyword argument 'request'" not in str(exc):
            raise
        return _baseline_state(net, bus_id, settings, tracker)


def _run_pandapower_power_flow(net: object, request: QstsRequest | None) -> None:
    import pandapower as pp

    kwargs: dict[str, object] = {
        "numba": request.pf_numba if request is not None else False,
    }
    algorithm = request.pf_algorithm if request is not None else "nr"
    if algorithm:
        kwargs["algorithm"] = algorithm
    pf_init = request.pf_init if request is not None else "auto"
    if pf_init != "auto":
        kwargs["init"] = pf_init
    if request is not None and request.pf_recycle:
        kwargs["recycle"] = {"bus_pq": True, "trafo": False, "gen": False}
    pp.runpp(net, **kwargs)


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
            return datetime(2026, 1, 1)
        return datetime(2026, 1, 1) + timedelta(hours=hour_index % 8760)


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


def _risk_summary_row(row: QstsRiskSummaryRow) -> dict[str, object]:
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


def _qsts_economics_row(request: QstsRequest, bus: QstsBusResult) -> dict[str, object]:
    economics = _qsts_bus_economics_proxy(request, bus)
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


def _decision_frontier_row(row: object) -> dict[str, object]:
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
        "frontier_verdict": row.frontier_verdict,
        "validation_level": row.validation_level,
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


def _render_investor_decision_table(
    buses: tuple[QstsBusResult, ...],
    request: QstsRequest,
    evaluated_time_steps: int = 0,
) -> str:
    lines = [
        "| rank | bus_id | qsts_verdict | validation_level | confidence | next_action | static_firm_mw | static_conditional_mw | qsts_p90_mw | qsts_mwh | main_constraint |",
        "| ---: | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for bus in buses:
        driver = _qsts_verdict_driver(
            bus.curtailment,
            p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
            mwh_tolerance=request.expected_curtailment_tolerance_mwh,
        )
        lines.append(
            "| "
            f"{bus.rank} | {bus.bus_id} | {bus.qsts_verdict} | "
            f"{_validation_level(request, evaluated_time_steps)} | "
            f"{_decision_confidence(request, evaluated_time_steps)} | "
            f"{_recommended_next_action(bus.qsts_verdict, driver, request, evaluated_time_steps)} | "
            f"{bus.static_firm_capacity_mw:.3f} | "
            f"{bus.static_conditional_capacity_mw:.3f} | "
            f"{bus.curtailment.p90_mw:.3f} | "
            f"{bus.curtailment.expected_mwh:.3f} | "
            f"{bus.main_recurring_constraint or '-'} |"
        )
    return "\n".join(lines)


def _render_risk_summary_table(rows: tuple[QstsRiskSummaryRow, ...]) -> str:
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


def _render_decision_drivers(rows: tuple[QstsRiskSummaryRow, ...]) -> str:
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
            f"{_driver_interpretation(row.verdict_driver, row.tail_risk_flag)} |"
        )
    return "\n".join(lines)


def _render_decision_snapshot(result: QstsResult) -> str:
    if not result.buses:
        return "No QSTS decision rows available."
    primary_bus = result.buses[0]
    primary_risk = summarize_qsts_risk(result)[0]
    lines = [
        f"- validation_level: {_validation_level(result.request, result.performance.evaluated_time_steps)}",
        f"- decision_confidence: {_decision_confidence(result.request, result.performance.evaluated_time_steps)}",
        "- investor_reference: qsts_full_year",
        "- recommended_next_action: "
        f"{_recommended_next_action(primary_bus.qsts_verdict, primary_risk.verdict_driver, result.request, result.performance.evaluated_time_steps)}",
        "",
        "| bus_id | verdict | p90_mw | expected_mwh | p95_mw | p99_mw | max_mw | dominant_constraint | recommended_next_action |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    risk_by_bus = {row.bus_id: row for row in summarize_qsts_risk(result)}
    for bus in result.buses:
        risk = risk_by_bus[bus.bus_id]
        lines.append(
            "| "
            f"{bus.bus_id} | {bus.qsts_verdict} | "
            f"{bus.curtailment.p90_mw:.3f} | {bus.curtailment.expected_mwh:.3f} | "
            f"{risk.curtailment_p95_mw:.3f} | {risk.curtailment_p99_mw:.3f} | "
            f"{risk.curtailment_max_mw:.3f} | {risk.dominant_constraint or '-'} | "
            f"{_recommended_next_action(bus.qsts_verdict, risk.verdict_driver, result.request, result.performance.evaluated_time_steps)} |"
        )
    return "\n".join(lines)


def _driver_interpretation(verdict_driver: str, tail_risk_flag: bool) -> str:
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


def _qsts_economics_proxy(result: QstsResult) -> QstsEconomicsProxy:
    bus = result.buses[0] if result.buses else None
    return _qsts_bus_economics_proxy(result.request, bus)


def _qsts_bus_economics_proxy(
    request: QstsRequest,
    bus: QstsBusResult | None,
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


def _render_qsts_economics_table(result: QstsResult) -> str:
    if not result.buses:
        return "No per-bus economics rows available."
    lines = [
        "| bus_id | verdict | weighted_mwh | annual_curtailment_loss | annual_ebitda_proxy | connect_now_value | wait_value | delta_npv |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for bus in result.buses:
        economics = _qsts_bus_economics_proxy(result.request, bus)
        lines.append(
            "| "
            f"{bus.bus_id} | {bus.qsts_verdict} | {bus.weighted_curtailment_mwh:.3f} | "
            f"{economics.annual_curtailment_loss_eur:.2f} | "
            f"{economics.annual_ebitda_proxy_eur:.2f} | "
            f"{economics.connect_now_value_eur:.2f} | "
            f"{economics.wait_value_eur:.2f} | {economics.delta_npv_eur:.2f} |"
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


def _series_quantile(values: pd.Series, quantile: float) -> float:
    if values.empty:
        return 0.0
    return round(float(values.quantile(quantile)), 6)


def _max_curtailment_event(frame: pd.DataFrame) -> tuple[int, float]:
    if frame.empty:
        return 0, 0.0
    worst_index = frame.groupby("timestamp")["curtailed_mw"].idxmax()
    worst = frame.loc[worst_index].copy()
    worst["curtailed_mw"] = worst["curtailed_mw"].astype(float).clip(lower=0.0)
    worst["event_timestamp"] = worst["timestamp"].map(_datetime_from_record_timestamp)
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


def _bus_max_curtailment_event(bus: QstsBusResult) -> tuple[int, float]:
    return _max_curtailment_event(pd.DataFrame(asdict(record) for record in bus.hourly_records))


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


def _qsts_verdict_driver(
    curtailment: CurtailmentEstimate,
    p90_tolerance_mw: float,
    mwh_tolerance: float,
) -> str:
    if curtailment.p90_mw <= 1e-9 and curtailment.expected_mwh <= 1e-9:
        return "no_curtailment"
    p90_exceeds = curtailment.p90_mw > p90_tolerance_mw + 1e-9
    mwh_exceeds = curtailment.expected_mwh > mwh_tolerance + 1e-9
    if p90_exceeds and mwh_exceeds:
        return "both_exceed"
    if p90_exceeds:
        return "p90_exceeds_tolerance"
    if mwh_exceeds:
        return "mwh_exceeds_tolerance"
    return "within_tolerance"


def _validation_level(request: QstsRequest, evaluated_time_steps: int | None = None) -> str:
    if request.stratified_sample:
        return "qsts_stratified"
    if (
        evaluated_time_steps is not None
        and evaluated_time_steps >= 8760
        and request.sample_every_n_hours == 1
    ):
        return "qsts_full_year"
    return "qsts_short"


def _decision_confidence(request: QstsRequest, evaluated_time_steps: int | None = None) -> str:
    level = _validation_level(request, evaluated_time_steps)
    if level == "qsts_full_year":
        return "high"
    if level == "qsts_stratified":
        return "medium"
    return "low"


def _recommended_next_action(
    qsts_verdict: str,
    verdict_driver: str,
    request: QstsRequest,
    evaluated_time_steps: int | None = None,
) -> str:
    if _validation_level(request, evaluated_time_steps) != "qsts_full_year":
        if qsts_verdict == "no-go":
            return "resize_or_run_full_year_validation"
        return "run_full_year_validation"
    if qsts_verdict == "go":
        return "proceed_to_investor_memo"
    if qsts_verdict == "go-with-conditions":
        return "proceed_with_conditions"
    if verdict_driver == "mwh_exceeds_tolerance":
        return "reject_or_resize_connection"
    return "reject_or_resize_connection"


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


def _bus_result_row(
    bus: QstsBusResult,
    request: QstsRequest,
    evaluated_time_steps: int = 0,
) -> dict[str, object]:
    driver = _qsts_verdict_driver(
        bus.curtailment,
        p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
        mwh_tolerance=request.expected_curtailment_tolerance_mwh,
    )
    return {
        "rank": bus.rank,
        "bus_id": bus.bus_id,
        "bus_name": bus.bus_name,
        "qsts_verdict": bus.qsts_verdict,
        "validation_level": _validation_level(request, evaluated_time_steps),
        "decision_confidence": _decision_confidence(request, evaluated_time_steps),
        "recommended_next_action": _recommended_next_action(
            bus.qsts_verdict,
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


def _investor_decision_row(
    bus: QstsBusResult,
    request: QstsRequest,
    evaluated_time_steps: int = 0,
) -> dict[str, object]:
    driver = _qsts_verdict_driver(
        bus.curtailment,
        p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
        mwh_tolerance=request.expected_curtailment_tolerance_mwh,
    )
    return {
        "rank": bus.rank,
        "bus_id": bus.bus_id,
        "bus_name": bus.bus_name,
        "qsts_verdict": bus.qsts_verdict,
        "validation_level": _validation_level(request, evaluated_time_steps),
        "decision_confidence": _decision_confidence(request, evaluated_time_steps),
        "recommended_next_action": _recommended_next_action(
            bus.qsts_verdict,
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


def _render_qsts_table(
    buses: tuple[QstsBusResult, ...],
    request: QstsRequest,
    evaluated_time_steps: int = 0,
) -> str:
    lines = [
        "| rank | bus_id | bus_name | qsts_verdict | validation_level | confidence | next_action | static_firm_mw | static_conditional_mw | qsts_p90_mw | qsts_mwh |",
        "| ---: | ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for bus in buses:
        driver = _qsts_verdict_driver(
            bus.curtailment,
            p90_tolerance_mw=request.p90_curtailment_tolerance_mw,
            mwh_tolerance=request.expected_curtailment_tolerance_mwh,
        )
        lines.append(
            "| "
            f"{bus.rank} | {bus.bus_id} | {bus.bus_name} | {bus.qsts_verdict} | "
            f"{_validation_level(request, evaluated_time_steps)} | "
            f"{_decision_confidence(request, evaluated_time_steps)} | "
            f"{_recommended_next_action(bus.qsts_verdict, driver, request, evaluated_time_steps)} | "
            f"{bus.static_firm_capacity_mw:.3f} | {bus.static_conditional_capacity_mw:.3f} | "
            f"{bus.curtailment.p90_mw:.3f} | {bus.curtailment.expected_mwh:.3f} |"
        )
    return "\n".join(lines)
