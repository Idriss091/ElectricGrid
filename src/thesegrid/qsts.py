from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from thesegrid.capacity import evaluate_dispatch, find_max_feasible
from thesegrid.constraints import ConstraintSettings
from thesegrid.gabarits import annual_timestamps
from thesegrid.models import CurtailmentEstimate, Direction
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
)


@dataclass(frozen=True)
class QstsRequest:
    network_code: str
    screening_csv: Path
    requested_mw: float
    top_n: int = 10
    asset: str = "bess"
    tolerance_mw: float = 0.05

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


@dataclass(frozen=True)
class QstsBusResult:
    rank: int
    bus_id: int
    bus_name: str
    qsts_verdict: str
    requested_mw: float
    static_firm_capacity_mw: float
    static_conditional_capacity_mw: float
    feasible_hours: int
    violation_hours: int
    curtailment: CurtailmentEstimate
    main_recurring_constraint: str
    hourly_records: tuple[QstsHourlyRecord, ...]


@dataclass(frozen=True)
class QstsResult:
    request: QstsRequest
    buses: tuple[QstsBusResult, ...]
    source: str = "actual hourly power-flow validation"


@dataclass(frozen=True)
class QstsOutputPaths:
    results_csv_path: Path
    summary_path: Path
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
    time_steps = _profile_time_steps(profiles)
    if not time_steps:
        raise ValueError("QSTS requires at least one profile time step")

    bus_results = tuple(
        _run_qsts_for_bus(
            network,
            selected,
            requested_mw=request.requested_mw,
            profiles=profiles,
            time_steps=time_steps,
            settings=settings,
            tolerance_mw=request.tolerance_mw,
        )
        for selected in selected_buses
    )
    return QstsResult(request=request, buses=bus_results)


def write_qsts_outputs(result: QstsResult, output_dir: Path) -> QstsOutputPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    results_csv = output_dir / "qsts_results.csv"
    summary_path = output_dir / "qsts_summary.md"
    detail_paths: list[Path] = []

    with results_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QSTS_RESULT_COLUMNS)
        writer.writeheader()
        for bus in result.buses:
            writer.writerow(_bus_result_row(bus))

    for bus in result.buses:
        detail_path = output_dir / f"qsts_bus_{bus.bus_id}.csv"
        with detail_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=QSTS_DETAIL_COLUMNS)
            writer.writeheader()
            for record in bus.hourly_records:
                writer.writerow(asdict(record))
        detail_paths.append(detail_path)

    summary_path.write_text(render_qsts_summary(result), encoding="utf-8")
    return QstsOutputPaths(
        results_csv_path=results_csv,
        summary_path=summary_path,
        bus_detail_paths=tuple(detail_paths),
    )


def render_qsts_summary(result: QstsResult) -> str:
    if not result.buses:
        top_table = "No buses selected for QSTS validation."
    else:
        top_table = _render_qsts_table(result.buses)
    return f"""# QSTS Top-N BESS Validation Summary

This report is based on {result.source}. It remains an early-stage buyer-side decision aid and does not replace an official grid-connection study.

## Request

- network_code: {result.request.network_code}
- requested_mw: {result.request.requested_mw:.3f}
- screening_csv: {result.request.screening_csv}
- top_n: {result.request.top_n}
- evaluated_buses: {len(result.buses)}

## Results

{top_table}

## Interpretation

- QSTS results replay time-varying network operating points before checking BESS injection and withdrawal.
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
) -> QstsBusResult:
    records: list[QstsHourlyRecord] = []
    constraint_counts: dict[str, int] = {}
    timestamps = _timestamps_for_steps(len(time_steps))

    for position, time_step in enumerate(time_steps):
        _apply_profiles(net, profiles, time_step)
        timestamp = timestamps[position]
        for direction in ("injection", "withdrawal"):
            requested = evaluate_dispatch(net, selected.bus_id, direction, requested_mw, settings)
            if requested.feasible:
                feasible_mw = requested_mw
                violations = requested.violations
            else:
                feasible_mw = find_max_feasible(
                    upper_mw=requested_mw,
                    is_feasible=lambda mw, direction=direction: evaluate_dispatch(
                        net, selected.bus_id, direction, mw, settings
                    ).feasible,
                    tolerance_mw=tolerance_mw,
                )
                violations = requested.violations
                if violations:
                    description = violations[0].description
                    constraint_counts[description] = constraint_counts.get(description, 0) + 1
            records.append(
                QstsHourlyRecord(
                    timestamp=str(timestamp),
                    direction=direction,
                    requested_mw=round(requested_mw, 6),
                    feasible_mw=round(feasible_mw, 6),
                    curtailed_mw=round(max(0.0, requested_mw - feasible_mw), 6),
                    converged=not any(v.element_type == "power_flow" for v in violations),
                    min_vm_pu=requested.min_vm_pu,
                    max_vm_pu=requested.max_vm_pu,
                    max_loading_percent=requested.max_loading_percent,
                    binding_constraint=violations[0].description if violations else "",
                )
            )

    hourly_frame = pd.DataFrame(asdict(record) for record in records)
    curtailment = qsts_curtailment_estimate(hourly_frame)
    total_hours = len(time_steps)
    feasible_hours = total_hours - curtailment.expected_hours
    qsts_verdict = _qsts_verdict(requested_mw, curtailment)
    return QstsBusResult(
        rank=selected.rank,
        bus_id=selected.bus_id,
        bus_name=selected.bus_name,
        qsts_verdict=qsts_verdict,
        requested_mw=round(requested_mw, 6),
        static_firm_capacity_mw=round(selected.firm_capacity_mw, 6),
        static_conditional_capacity_mw=round(selected.conditional_capacity_mw, 6),
        feasible_hours=feasible_hours,
        violation_hours=curtailment.expected_hours,
        curtailment=curtailment,
        main_recurring_constraint=_main_recurring_constraint(constraint_counts),
        hourly_records=tuple(records),
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


def _profile_time_steps(profiles: dict[str, pd.DataFrame]) -> tuple[int, ...]:
    lengths = [len(frame) for frame in profiles.values() if not frame.empty]
    if not lengths:
        return ()
    return tuple(range(min(lengths)))


def _timestamps_for_steps(count: int) -> tuple[str | int, ...]:
    if count == 8760:
        return tuple(timestamp.isoformat() for timestamp in annual_timestamps(2026))
    return tuple(range(count))


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


def _qsts_verdict(requested_mw: float, curtailment: CurtailmentEstimate) -> str:
    if curtailment.p90_mw <= 1e-9:
        return "go"
    if curtailment.p90_mw < requested_mw:
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
        "feasible_hours": bus.feasible_hours,
        "violation_hours": bus.violation_hours,
        "expected_curtailment_mwh": f"{bus.curtailment.expected_mwh:.6f}",
        "p50_curtailment_mw": f"{bus.curtailment.p50_mw:.6f}",
        "p90_curtailment_mw": f"{bus.curtailment.p90_mw:.6f}",
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
