from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from thesegrid.capacity import DispatchEvaluation, evaluate_dispatch
from thesegrid.contractual import synthesize_contractual_envelope
from thesegrid.constraints import ConstraintSettings, check_constraints
from thesegrid.decision_frontier import decision_frontier_rows
from thesegrid.gabarits import GabaritKind, is_restricted
from thesegrid.models import ConstraintViolation, CurtailmentEstimate, Direction
from thesegrid.networks import ToyNetwork, load_network
from thesegrid.qsts_curtailment import (
    qsts_curtailment_estimate,
    weighted_qsts_curtailment_estimate,
)
from thesegrid.qsts_decisions import (
    decision_confidence as _decision_confidence,
    qsts_verdict as _qsts_verdict,
    qsts_verdict_driver as _qsts_verdict_driver,
    recommended_next_action as _recommended_next_action,
    validation_level as _validation_level,
)
from thesegrid.qsts_economics import qsts_economics_proxy as _qsts_economics_proxy
from thesegrid.qsts_profiles import (
    apply_profiles as _apply_profiles,
    available_profile_hours as _available_profile_hours,
    profile_time_steps as _profile_time_steps,
    time_step_weights as _profile_time_step_weights,
    timestamp_weights as _timestamp_weights,
    timestamps_for_steps as _timestamps_for_steps,
    to_hourly_profile as _to_hourly_profile,
)
from thesegrid.qsts_reporting import (
    CONTRACTUAL_ENVELOPE_COLUMNS,
    INVESTOR_DECISION_COLUMNS,
    QSTS_DETAIL_COLUMNS,
    QSTS_ECONOMICS_COLUMNS,
    QSTS_ENVELOPE_COLUMNS,
    QSTS_ENVELOPE_SUMMARY_COLUMNS,
    QSTS_RESULT_COLUMNS,
    QSTS_RISK_SUMMARY_COLUMNS,
    STATIC_VS_QSTS_COMPARISON_COLUMNS,
    bus_max_curtailment_event as _bus_max_curtailment_event,
    bus_result_row as _bus_result_row,
    contractual_envelope_row as _contractual_envelope_row,
    datetime_from_record_timestamp as _datetime_from_record_timestamp,
    decision_frontier_row as _decision_frontier_row,
    dominant_string as _dominant_string,
    envelope_record_row as _envelope_record_row,
    envelope_summary_row as _envelope_summary_row,
    investor_decision_row as _investor_decision_row,
    json_ready as _json_ready,
    max_curtailment_event as _max_curtailment_event,
    qsts_economics_row as _qsts_economics_row,
    render_baseline_table as _render_baseline_table,
    render_contractual_envelope_table as _render_contractual_envelope_table,
    render_contractual_summary_table as _render_contractual_summary_table,
    render_decision_drivers as _render_decision_drivers,
    render_decision_snapshot as _render_decision_snapshot,
    render_envelope_comparison_table as _render_envelope_comparison_table,
    render_investor_decision_table as _render_investor_decision_table,
    render_qsts_economics_table as _render_qsts_economics_table,
    render_qsts_investment_table as _render_qsts_investment_table,
    render_qsts_table as _render_qsts_table,
    render_risk_summary_table as _render_risk_summary_table,
    risk_summary_row as _risk_summary_row,
    selected_policy_verdict as _selected_policy_verdict,
    static_vs_qsts_comparison_rows as _static_vs_qsts_comparison_rows,
    write_run_manifest as _write_run_manifest,
)
from thesegrid.risk import estimate_curtailment


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
    profile_year: int = 2026
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
    selected_policy: str = "standard"

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
        if not 1900 <= self.profile_year <= 2100:
            raise ValueError("profile_year must be between 1900 and 2100")
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
        if self.selected_policy not in {"strict", "standard", "flexible", "aggressive"}:
            raise ValueError("selected_policy must be strict, standard, flexible, or aggressive")


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
        profile_year=request.profile_year,
    )
    if not time_steps:
        raise ValueError("QSTS requires at least one profile time step")
    timestamp_weights = _timestamp_weights(
        time_steps,
        _time_step_weights(time_steps, request, _available_profile_hours(profiles)),
        profile_year=request.profile_year,
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
                profile_year=request.profile_year,
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
        primary_decision = _selected_policy_verdict(
            result.buses[0],
            result.request,
            result.performance.evaluated_time_steps,
        )
        recommended_next_action = _recommended_next_action(
            primary_decision,
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
- profile_year: {result.request.profile_year}
- tolerance_mw: {result.request.tolerance_mw:.3f}
- p90_curtailment_tolerance_mw: {result.request.p90_curtailment_tolerance_mw:.3f}
- expected_curtailment_tolerance_mwh: {result.request.expected_curtailment_tolerance_mwh:.3f}
- selected_policy: {result.request.selected_policy}
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
        product_decision = _selected_policy_verdict(
            top_bus,
            result.request,
            result.performance.evaluated_time_steps,
        )
        primary = (
            f"Bus {top_bus.bus_id} ({top_bus.bus_name or 'unnamed'}) is the top-ranked "
            f"QSTS candidate with product decision `{product_decision}` under the "
            f"`{result.request.selected_policy}` policy at {top_bus.requested_mw:.3f} MW. "
            f"Legacy QSTS verdict: `{top_bus.qsts_verdict}`."
        )
        contractual_rows = synthesize_contractual_envelope(qsts_envelope_records(result)).rows
        investor_table = _render_qsts_investment_table(result, contractual_rows)
        contractual_summary = _render_contractual_summary_table(contractual_rows)
        contractual_detail = _render_contractual_envelope_table(contractual_rows)
        decision_drivers = _render_decision_drivers(summarize_qsts_risk(result))
        decision_snapshot = _render_decision_snapshot(result, summarize_qsts_risk(result))
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
- selected_policy: {result.request.selected_policy}
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
    profile_year: int = 2026,
) -> QstsBusResult:
    records: list[QstsHourlyRecord] = []
    constraint_counts: dict[str, int] = {}
    baseline_constraint_counts: dict[str, int] = {}
    baseline_violating_hours = 0
    baseline_max_vm_pu: float | None = None
    baseline_max_loading_percent: float | None = None
    timestamps = _timestamps_for_steps(time_steps, profile_year=profile_year)
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


def _time_step_weights(
    time_steps: tuple[int, ...],
    request: QstsRequest,
    available_hours: int,
) -> dict[int, float]:
    return _profile_time_step_weights(
        time_steps,
        stratified_sample=request.stratified_sample,
        available_hours=available_hours,
        profile_year=request.profile_year,
    )


def _curtailment_energy_ratio(weighted_curtailment_mwh: float, requested_mw: float) -> float:
    denominator = requested_mw * 8760.0
    if denominator <= 0:
        return 0.0
    return round(weighted_curtailment_mwh / denominator, 6)


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
    if _baseline_power_flow_unusable(baseline):
        return _IncrementalDispatchEvaluation(
            incrementally_feasible=False,
            incremental_violations=("baseline_unusable: power_flow[-1] converged=0.000",),
            binding_constraint="baseline_unusable: power_flow[-1] converged=0.000",
            min_vm_pu=None,
            max_vm_pu=None,
            max_loading_percent=None,
            converged=False,
        )
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


def _baseline_power_flow_unusable(baseline: dict[tuple[str, int, str], float]) -> bool:
    value = baseline.get(("power_flow", -1, "converged"))
    return value is not None and value < 1.0


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


def _series_quantile(values: pd.Series, quantile: float) -> float:
    if values.empty:
        return 0.0
    return round(float(values.quantile(quantile)), 6)


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


def _main_recurring_constraint(counts: dict[str, int]) -> str:
    if not counts:
        return ""
    constraint, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return f"{constraint}: count={count}"
