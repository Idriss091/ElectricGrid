from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from thesegrid.constraints import ConstraintSettings
from thesegrid.decision_frontier import decision_frontier_rows
from thesegrid.qsts import (
    QstsRequest,
    _bus_max_curtailment_event,
    _decision_confidence,
    _qsts_economics_proxy,
    _qsts_verdict_driver,
    _recommended_next_action,
    _validation_level,
    run_qsts,
    write_qsts_outputs,
)


RESIZE_RESULT_COLUMNS = (
    "requested_mw",
    "original_requested_mw",
    "delta_mw_from_original",
    "bus_id",
    "bus_name",
    "qsts_verdict",
    "legacy_qsts_verdict",
    "selected_policy",
    "strict_policy_verdict",
    "standard_policy_verdict",
    "flexible_policy_verdict",
    "aggressive_policy_verdict",
    "product_decision",
    "acceptable",
    "validation_level",
    "decision_confidence",
    "recommended_next_action",
    "expected_curtailment_mwh",
    "p90_curtailment_mw",
    "verdict_driver",
    "main_recurring_constraint",
    "delta_npv_eur",
    "runtime_seconds",
    "qsts_output_dir",
)


@dataclass(frozen=True)
class ResizeRequest:
    network_code: str
    screening_csv: Path
    bus_id: int
    original_requested_mw: float
    min_mw: float
    step_mw: float
    output_dir: Path
    asset: str = "bess"
    start_hour: int = 0
    duration_hours: int | None = None
    profile_year: int = 2026
    sample_every_n_hours: int = 1
    stratified_sample: bool = False
    progress_every_n_hours: int = 250
    p90_curtailment_tolerance_mw: float = 0.0
    expected_curtailment_tolerance_mwh: float = 0.0
    storage_duration_hours: float = 4.0
    capex_eur_per_kw: float = 0.0
    fixed_opex_eur_per_kw_year: float = 0.0
    gross_revenue_eur_per_mw_year: float = 0.0
    curtailment_penalty_eur_per_mwh: float = 100.0
    reinforcement_wait_years: float = 5.0
    discount_rate: float = 0.08
    selected_policy: str = "standard"
    pf_numba: bool = False
    pf_algorithm: str = "nr"
    pf_init: str = "auto"
    pf_recycle: bool = False

    def __post_init__(self) -> None:
        resize_mw_values(self.original_requested_mw, self.min_mw, self.step_mw)
        if self.bus_id < 0:
            raise ValueError("bus_id must be non-negative")
        if not 1900 <= self.profile_year <= 2100:
            raise ValueError("profile_year must be between 1900 and 2100")
        if self.selected_policy not in {"strict", "standard", "flexible", "aggressive"}:
            raise ValueError("selected_policy must be strict, standard, flexible, or aggressive")


@dataclass(frozen=True)
class ResizeResult:
    request: ResizeRequest
    rows: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ResizeOutputPaths:
    csv_path: Path
    summary_path: Path


def run_resize_scenarios(
    request: ResizeRequest,
    settings: ConstraintSettings,
    *,
    qsts_runner: Callable[..., object] = run_qsts,
) -> ResizeResult:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for requested_mw in resize_mw_values(
        request.original_requested_mw,
        request.min_mw,
        request.step_mw,
    ):
        scenario_id = f"mw_{_slug_mw(requested_mw)}"
        scenario_dir = request.output_dir / scenario_id
        qsts_request = _resize_qsts_request(request, requested_mw)
        qsts_result = qsts_runner(qsts_request, settings=settings)
        write_qsts_outputs(
            qsts_result,
            scenario_dir,
            command=(
                "qsts-resize",
                "--requested-mw",
                f"{requested_mw:.6f}",
                "--scenario",
                scenario_id,
            ),
        )
        rows.append(
            resize_result_row(
                qsts_result,
                scenario_dir,
                request.original_requested_mw,
                selected_policy=request.selected_policy,
            )
        )
    return ResizeResult(request=request, rows=tuple(rows))


def write_resize_outputs(result: ResizeResult, output_dir: Path) -> ResizeOutputPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    results_csv = output_dir / "resize_results.csv"
    write_resize_results(results_csv, list(result.rows))
    summary_path = output_dir / "resize_summary.md"
    summary_path.write_text(
        render_resize_summary(
            rows=list(result.rows),
            bus_id=result.request.bus_id,
            original_requested_mw=result.request.original_requested_mw,
        ),
        encoding="utf-8",
    )
    return ResizeOutputPaths(csv_path=results_csv, summary_path=summary_path)


def resize_mw_values(requested_mw: float, min_mw: float, step_mw: float) -> list[float]:
    if requested_mw <= 0:
        raise ValueError("requested_mw must be positive")
    if min_mw <= 0:
        raise ValueError("min_mw must be positive")
    if min_mw > requested_mw:
        raise ValueError("min_mw must be less than or equal to requested_mw")
    if step_mw <= 0:
        raise ValueError("step_mw must be positive")

    values: list[float] = []
    current = requested_mw
    while current >= min_mw - 1e-9:
        values.append(round(current, 6))
        current -= step_mw
    if abs(values[-1] - min_mw) > 1e-9:
        values.append(round(min_mw, 6))
    return values


def resize_result_row(
    result: object,
    scenario_dir: Path,
    original_requested_mw: float,
    *,
    selected_policy: str,
) -> dict[str, object]:
    if not result.buses:
        raise ValueError("qsts-resize scenario returned no bus results")
    bus = result.buses[0]
    driver = _qsts_verdict_driver(
        bus.curtailment,
        p90_tolerance_mw=result.request.p90_curtailment_tolerance_mw,
        mwh_tolerance=result.request.expected_curtailment_tolerance_mwh,
    )
    economics = _qsts_economics_proxy(result)
    policy_verdicts = resize_policy_verdicts(
        result.request,
        bus,
        evaluated_time_steps=result.performance.evaluated_time_steps,
    )
    selected_policy_verdict = policy_verdicts.get(selected_policy, bus.qsts_verdict)
    product_decision = resize_product_decision(
        selected_policy_verdict,
        requested_mw=result.request.requested_mw,
        original_requested_mw=original_requested_mw,
    )
    return {
        "requested_mw": f"{result.request.requested_mw:.6f}",
        "original_requested_mw": f"{original_requested_mw:.6f}",
        "delta_mw_from_original": f"{max(original_requested_mw - result.request.requested_mw, 0.0):.6f}",
        "bus_id": bus.bus_id,
        "bus_name": bus.bus_name,
        "qsts_verdict": bus.qsts_verdict,
        "legacy_qsts_verdict": bus.qsts_verdict,
        "selected_policy": selected_policy,
        "strict_policy_verdict": policy_verdicts.get("strict", ""),
        "standard_policy_verdict": policy_verdicts.get("standard", ""),
        "flexible_policy_verdict": policy_verdicts.get("flexible", ""),
        "aggressive_policy_verdict": policy_verdicts.get("aggressive", ""),
        "product_decision": product_decision,
        "acceptable": str(resize_acceptable(selected_policy_verdict)),
        "validation_level": _validation_level(result.request, result.performance.evaluated_time_steps),
        "decision_confidence": _decision_confidence(
            result.request,
            result.performance.evaluated_time_steps,
        ),
        "recommended_next_action": _recommended_next_action(
            bus.qsts_verdict,
            driver,
            result.request,
            result.performance.evaluated_time_steps,
        ),
        "expected_curtailment_mwh": f"{bus.curtailment.expected_mwh:.6f}",
        "p90_curtailment_mw": f"{bus.curtailment.p90_mw:.6f}",
        "verdict_driver": driver,
        "main_recurring_constraint": bus.main_recurring_constraint,
        "delta_npv_eur": f"{economics.delta_npv_eur:.6f}",
        "runtime_seconds": f"{result.performance.runtime_seconds:.6f}",
        "qsts_output_dir": scenario_dir.as_posix(),
    }


def resize_acceptable(qsts_verdict: str) -> bool:
    return qsts_verdict in {"go", "go-with-conditions"}


def resize_policy_verdicts(
    request: QstsRequest,
    bus: object,
    evaluated_time_steps: int | None,
) -> dict[str, str]:
    max_event_hours, max_event_mwh = _bus_max_curtailment_event(bus)
    rows = decision_frontier_rows(
        bus_id=bus.bus_id,
        bus_name=bus.bus_name,
        requested_mw=bus.requested_mw,
        qsts_p90_mw=bus.curtailment.p90_mw,
        weighted_curtailment_mwh=bus.weighted_curtailment_mwh,
        curtailment_energy_ratio=bus.curtailment_energy_ratio,
        max_event_hours=max_event_hours,
        max_event_mwh=max_event_mwh,
        validation_level=_validation_level(request, evaluated_time_steps),
    )
    return {row.policy: row.frontier_verdict for row in rows}


def resize_product_decision(
    qsts_verdict: str,
    requested_mw: float,
    original_requested_mw: float,
) -> str:
    if not resize_acceptable(qsts_verdict):
        return "no-go"
    if requested_mw < original_requested_mw - 1e-9:
        return "resize-recommended"
    return qsts_verdict


def write_resize_results(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESIZE_RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def render_resize_summary(
    rows: list[dict[str, object]],
    bus_id: int,
    original_requested_mw: float,
) -> str:
    recommended = recommended_resize_row(rows)
    if recommended is None:
        recommendation = (
            f"Bus {bus_id} is not acceptable at {original_requested_mw:.3f} MW and no "
            "tested lower MW met the selected decision-frontier policy."
        )
        recommended_line = "- recommended_resized_mw: none"
    else:
        recommended_mw = float(str(recommended["requested_mw"]))
        delta_mw = float(str(recommended["delta_mw_from_original"]))
        selected_policy = str(recommended["selected_policy"])
        selected_policy_verdict = str(recommended[f"{selected_policy}_policy_verdict"])
        recommendation = (
            f"Bus {bus_id} is not acceptable at {original_requested_mw:.3f} MW, but is "
            f"acceptable at {recommended_mw:.3f} MW under selected policy "
            f"`{selected_policy}` with policy verdict `{selected_policy_verdict}`."
        )
        recommended_line = (
            f"- product_decision: {recommended['product_decision']}\n"
            f"- selected_policy: {selected_policy}\n"
            f"- selected_policy_verdict: {selected_policy_verdict}\n"
            f"- recommended_resized_mw: {recommended_mw:.3f}\n"
            f"- delta_mw_from_original: {delta_mw:.3f}\n"
            f"- delta_npv_eur: {float(str(recommended['delta_npv_eur'])):.2f}"
        )
    return f"""# QSTS Resize Summary

This resize workflow is a buyer-side pre-feasibility aid. It does not replace an
official connection study or PTF.

## Recommendation

{recommended_line}
- original_requested_mw: {original_requested_mw:.3f}
- bus_id: {bus_id}

{recommendation}

## Tested MW

{render_resize_table(rows)}
"""


def recommended_resize_row(rows: list[dict[str, object]]) -> dict[str, object] | None:
    acceptable = [row for row in rows if row["acceptable"] == "True"]
    if not acceptable:
        return None
    return max(acceptable, key=lambda row: float(str(row["requested_mw"])))


def render_resize_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No resize scenarios were evaluated."
    lines = [
        "| requested_mw | product_decision | verdict | acceptable | expected_mwh | p90_mw | delta_npv_eur | driver | output |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{float(str(row['requested_mw'])):.3f} | {row['product_decision']} | "
            f"{row['qsts_verdict']} | "
            f"{row['acceptable']} | {float(str(row['expected_curtailment_mwh'])):.3f} | "
            f"{float(str(row['p90_curtailment_mw'])):.3f} | "
            f"{float(str(row['delta_npv_eur'])):.2f} | {row['verdict_driver']} | "
            f"{row['qsts_output_dir']} |"
        )
    return "\n".join(lines)


def _resize_qsts_request(request: ResizeRequest, requested_mw: float) -> QstsRequest:
    return QstsRequest(
        network_code=request.network_code,
        screening_csv=request.screening_csv,
        requested_mw=requested_mw,
        top_n=1,
        bus_ids=(request.bus_id,),
        asset=request.asset,
        start_hour=request.start_hour,
        duration_hours=request.duration_hours,
        profile_year=request.profile_year,
        sample_every_n_hours=request.sample_every_n_hours,
        stratified_sample=request.stratified_sample,
        progress_every_n_hours=request.progress_every_n_hours,
        p90_curtailment_tolerance_mw=request.p90_curtailment_tolerance_mw,
        expected_curtailment_tolerance_mwh=request.expected_curtailment_tolerance_mwh,
        storage_duration_hours=request.storage_duration_hours,
        capex_eur_per_kw=request.capex_eur_per_kw,
        fixed_opex_eur_per_kw_year=request.fixed_opex_eur_per_kw_year,
        gross_revenue_eur_per_mw_year=request.gross_revenue_eur_per_mw_year,
        curtailment_penalty_eur_per_mwh=request.curtailment_penalty_eur_per_mwh,
        reinforcement_wait_years=request.reinforcement_wait_years,
        discount_rate=request.discount_rate,
        pf_numba=request.pf_numba,
        pf_algorithm=request.pf_algorithm,
        pf_init=request.pf_init,
        pf_recycle=request.pf_recycle,
    )


def _slug_mw(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".").replace(".", "p")
