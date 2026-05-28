from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from shutil import copyfile

from thesegrid.bess import BessLiteAssumptions
from thesegrid.bundle import write_bundle_report
from thesegrid.constraints import ConstraintSettings
from thesegrid.evidence import DataSourceType, EvidenceProfile, evidence_profile
from thesegrid.full_year_selection import (
    DEFAULT_FULL_YEAR_BAD_CONTROLS,
    DEFAULT_FULL_YEAR_BORDERLINE_CANDIDATES,
    DEFAULT_FULL_YEAR_FALSE_POSITIVE_SUSPECTS,
    DEFAULT_FULL_YEAR_MAX_CANDIDATES,
    DEFAULT_FULL_YEAR_TOP_CANDIDATES,
    FullYearCandidate,
    FullYearSelectionRequest,
    select_full_year_candidates,
    write_full_year_selection_csv,
)
from thesegrid.models import EconomicAssumptions
from thesegrid.qsts import QstsRequest, run_qsts, write_qsts_outputs
from thesegrid.resize import ResizeRequest, run_resize_scenarios, write_resize_outputs
from thesegrid.screening import ScreeningRequest, screen_connections, write_screening_outputs
from thesegrid.stratified_selection import (
    DEFAULT_STRATIFIED_BORDERLINE_CANDIDATES,
    DEFAULT_STRATIFIED_CONSTRAINT_DIVERSE_CANDIDATES,
    DEFAULT_STRATIFIED_MAX_CANDIDATES,
    DEFAULT_STRATIFIED_NEAR_THRESHOLD_NO_GO_CANDIDATES,
    DEFAULT_STRATIFIED_TOP_GO_CANDIDATES,
    StratifiedCandidate,
    StratifiedSelectionRequest,
    select_stratified_candidates,
    write_stratified_selection_csv,
)
from thesegrid.validation_matrix import build_validation_matrix, write_validation_matrix_outputs


@dataclass(frozen=True)
class PipelineRequest:
    network_code: str
    requested_mw: float
    output_dir: Path
    asset: str = "bess"
    top_n: int = 10
    max_buses: int | None = None
    candidate_policy: str = "mv_active"
    data_source_type: DataSourceType = "benchmark"
    curtailment_tolerance_mwh_per_year: float = 0.0
    p90_curtailment_tolerance_mw: float = 0.0
    reinforcement_wait_years: float = 5.0
    economics: EconomicAssumptions = field(default_factory=EconomicAssumptions)
    storage_duration_hours: float = 4.0
    round_trip_efficiency: float = 0.9
    soc_min_fraction: float = 0.0
    soc_max_fraction: float = 1.0
    run_qsts_stratified: bool = False
    qsts_start_hour: int = 0
    qsts_duration_hours: int | None = None
    qsts_sample_every_n_hours: int = 1
    qsts_progress_every_n_hours: int = 250
    qsts_voltage_min_pu: float = 0.95
    qsts_voltage_max_pu: float = 1.05
    qsts_max_loading_percent: float = 100.0
    qsts_p90_curtailment_tolerance_mw: float = 0.0
    qsts_expected_curtailment_tolerance_mwh: float = 0.0
    run_qsts_full_year: bool = False
    stratified_max_candidates: int = DEFAULT_STRATIFIED_MAX_CANDIDATES
    stratified_top_go_candidates: int = DEFAULT_STRATIFIED_TOP_GO_CANDIDATES
    stratified_borderline_candidates: int = DEFAULT_STRATIFIED_BORDERLINE_CANDIDATES
    stratified_near_threshold_no_go_candidates: int = (
        DEFAULT_STRATIFIED_NEAR_THRESHOLD_NO_GO_CANDIDATES
    )
    stratified_constraint_diverse_candidates: int = (
        DEFAULT_STRATIFIED_CONSTRAINT_DIVERSE_CANDIDATES
    )
    full_year_max_candidates: int = DEFAULT_FULL_YEAR_MAX_CANDIDATES
    full_year_top_candidates: int = DEFAULT_FULL_YEAR_TOP_CANDIDATES
    full_year_borderline_candidates: int = DEFAULT_FULL_YEAR_BORDERLINE_CANDIDATES
    full_year_false_positive_suspects: int = DEFAULT_FULL_YEAR_FALSE_POSITIVE_SUSPECTS
    full_year_bad_controls: int = DEFAULT_FULL_YEAR_BAD_CONTROLS
    run_resize_on_no_go: bool = False
    resize_min_mw: float = 1.0
    resize_step_mw: float = 1.0
    resize_selected_policy: str = "standard"
    resize_max_buses: int = 1

    def __post_init__(self) -> None:
        if not self.network_code:
            raise ValueError("network_code must not be empty")
        if self.requested_mw <= 0:
            raise ValueError("requested_mw must be positive")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")
        if self.run_qsts_full_year and not self.run_qsts_stratified:
            raise ValueError("run_qsts_full_year requires run_qsts_stratified")
        if self.run_resize_on_no_go and not self.run_qsts_full_year:
            raise ValueError("run_resize_on_no_go requires run_qsts_full_year")
        if self.resize_max_buses <= 0:
            raise ValueError("resize_max_buses must be positive")
        evidence_profile(evidence_level="screening_only", data_source_type=self.data_source_type)
        self.bess_lite()

    def bess_lite(self) -> BessLiteAssumptions:
        return BessLiteAssumptions(
            power_mw=self.requested_mw,
            duration_hours=self.storage_duration_hours,
            round_trip_efficiency=self.round_trip_efficiency,
            soc_min_fraction=self.soc_min_fraction,
            soc_max_fraction=self.soc_max_fraction,
        )


@dataclass(frozen=True)
class PipelineResult:
    output_dir: Path
    report_path: Path
    manifest_path: Path
    screening_csv_path: Path
    screening_summary_path: Path
    stratified_selection_csv_path: Path
    qsts_stratified_results_csv_path: Path | None = None
    qsts_stratified_summary_path: Path | None = None
    qsts_stratified_manifest_path: Path | None = None
    qsts_stratified_memo_path: Path | None = None
    full_year_selection_csv_path: Path | None = None
    qsts_full_year_results_csv_path: Path | None = None
    qsts_full_year_summary_path: Path | None = None
    qsts_full_year_manifest_path: Path | None = None
    qsts_full_year_memo_path: Path | None = None
    validation_matrix_csv_path: Path | None = None
    validation_matrix_markdown_path: Path | None = None
    resize_results_csv_path: Path | None = None
    resize_summary_path: Path | None = None
    investor_report_html_path: Path | None = None
    scorecard_path: Path | None = None
    campaign_guide_path: Path | None = None


def run_pipeline(request: PipelineRequest) -> PipelineResult:
    """Run the first product pipeline tranche.

    This intentionally stops before QSTS. It turns the existing static screening and
    balanced stratified-candidate selection into one reproducible workflow.
    """
    request.output_dir.mkdir(parents=True, exist_ok=True)
    screening_dir = request.output_dir / "screening"
    screening_result = screen_connections(
        ScreeningRequest(
            network_code=request.network_code,
            requested_mw=request.requested_mw,
            asset=request.asset,
            top_n=request.top_n,
            max_buses=request.max_buses,
            candidate_policy=request.candidate_policy,
            curtailment_tolerance_mwh_per_year=request.curtailment_tolerance_mwh_per_year,
            p90_curtailment_tolerance_mw=request.p90_curtailment_tolerance_mw,
            reinforcement_wait_years=request.reinforcement_wait_years,
            economics=request.economics,
        )
    )
    screening_outputs = write_screening_outputs(screening_result, screening_dir)

    stratified_candidates = select_stratified_candidates(
        StratifiedSelectionRequest(
            screening_csv=screening_outputs.csv_path,
            max_candidates=request.stratified_max_candidates,
            top_go_candidates=request.stratified_top_go_candidates,
            borderline_candidates=request.stratified_borderline_candidates,
            near_threshold_no_go_candidates=request.stratified_near_threshold_no_go_candidates,
            constraint_diverse_candidates=request.stratified_constraint_diverse_candidates,
        )
    )
    stratified_selection_csv = request.output_dir / "stratified_candidate_selection.csv"
    write_stratified_selection_csv(stratified_candidates, stratified_selection_csv)

    qsts_outputs = None
    qsts_full_year_outputs = None
    validation_outputs = None
    resize_outputs = None
    bundle_outputs = None
    full_year_candidates: tuple[FullYearCandidate, ...] = ()
    full_year_selection_csv = None
    if request.run_qsts_stratified:
        qsts_result = run_qsts(
            _qsts_stratified_request(request, screening_outputs.csv_path, stratified_candidates),
            settings=ConstraintSettings(
                min_vm_pu=request.qsts_voltage_min_pu,
                max_vm_pu=request.qsts_voltage_max_pu,
                max_loading_percent=request.qsts_max_loading_percent,
            ),
        )
        qsts_outputs = write_qsts_outputs(
            qsts_result,
            request.output_dir / "qsts_stratified",
            command=("run-pipeline", "qsts-stratified"),
        )
        full_year_candidates = select_full_year_candidates(
            FullYearSelectionRequest(
                screening_csv=screening_outputs.csv_path,
                stratified_csv=qsts_outputs.results_csv_path,
                max_candidates=request.full_year_max_candidates,
                top_candidates=request.full_year_top_candidates,
                borderline_candidates=request.full_year_borderline_candidates,
                false_positive_suspects=request.full_year_false_positive_suspects,
                bad_controls=request.full_year_bad_controls,
            )
        )
        full_year_selection_csv = request.output_dir / "full_year_candidate_selection.csv"
        write_full_year_selection_csv(full_year_candidates, full_year_selection_csv)
        if request.run_qsts_full_year:
            qsts_full_year_result = run_qsts(
                _qsts_full_year_request(
                    request,
                    screening_outputs.csv_path,
                    full_year_candidates,
                ),
                settings=ConstraintSettings(
                    min_vm_pu=request.qsts_voltage_min_pu,
                    max_vm_pu=request.qsts_voltage_max_pu,
                    max_loading_percent=request.qsts_max_loading_percent,
                ),
            )
            qsts_full_year_outputs = write_qsts_outputs(
                qsts_full_year_result,
                request.output_dir / "qsts_full_year",
                command=("run-pipeline", "qsts-full-year"),
            )
            validation_matrix = build_validation_matrix(
                screening_csv=screening_outputs.csv_path,
                qsts_stratified_csv=qsts_outputs.results_csv_path,
                qsts_full_year_csvs=(qsts_full_year_outputs.results_csv_path,),
                decision_frontier_csvs=_existing_output_paths(
                    qsts_full_year_outputs,
                    "decision_frontier_csv_path",
                ),
                selected_policy="standard",
            )
            validation_outputs = write_validation_matrix_outputs(
                validation_matrix,
                request.output_dir / "validation",
            )
            if request.run_resize_on_no_go:
                no_go_buses = tuple(
                    bus for bus in qsts_full_year_result.buses if bus.qsts_verdict == "no-go"
                )
                if no_go_buses:
                    resize_bus = no_go_buses[0]
                    resize_result = run_resize_scenarios(
                        ResizeRequest(
                            network_code=request.network_code,
                            screening_csv=screening_outputs.csv_path,
                            bus_id=resize_bus.bus_id,
                            original_requested_mw=request.requested_mw,
                            min_mw=request.resize_min_mw,
                            step_mw=request.resize_step_mw,
                            output_dir=request.output_dir
                            / "resize"
                            / "scenarios"
                            / f"bus_{resize_bus.bus_id}",
                            asset=request.asset,
                            start_hour=0,
                            duration_hours=None,
                            sample_every_n_hours=1,
                            stratified_sample=False,
                            progress_every_n_hours=request.qsts_progress_every_n_hours,
                            p90_curtailment_tolerance_mw=(
                                request.qsts_p90_curtailment_tolerance_mw
                            ),
                            expected_curtailment_tolerance_mwh=(
                                request.qsts_expected_curtailment_tolerance_mwh
                            ),
                            storage_duration_hours=request.storage_duration_hours,
                            curtailment_penalty_eur_per_mwh=(
                                request.economics.curtailment_penalty_eur_per_mwh
                            ),
                            reinforcement_wait_years=request.reinforcement_wait_years,
                            selected_policy=request.resize_selected_policy,
                        ),
                        settings=ConstraintSettings(
                            min_vm_pu=request.qsts_voltage_min_pu,
                            max_vm_pu=request.qsts_voltage_max_pu,
                            max_loading_percent=request.qsts_max_loading_percent,
                        ),
                    )
                    resize_outputs = write_resize_outputs(
                        resize_result,
                        request.output_dir / "resize",
                    )
                    _copy_if_available(resize_outputs.csv_path, request.output_dir / "resize_results.csv")
                    _copy_if_available(resize_outputs.summary_path, request.output_dir / "resize_summary.md")
            _prepare_bundle_inputs(
                output_dir=request.output_dir,
                validation_outputs=validation_outputs,
                qsts_outputs=qsts_full_year_outputs,
            )
            bundle_outputs = write_bundle_report(request.output_dir)

    report_path = request.output_dir / "pipeline_report.md"
    manifest_path = request.output_dir / "pipeline_manifest.json"
    result = PipelineResult(
        output_dir=request.output_dir,
        report_path=report_path,
        manifest_path=manifest_path,
        screening_csv_path=screening_outputs.csv_path,
        screening_summary_path=screening_outputs.summary_path,
        stratified_selection_csv_path=stratified_selection_csv,
        qsts_stratified_results_csv_path=(
            None if qsts_outputs is None else qsts_outputs.results_csv_path
        ),
        qsts_stratified_summary_path=None if qsts_outputs is None else qsts_outputs.summary_path,
        qsts_stratified_manifest_path=(
            None if qsts_outputs is None else qsts_outputs.run_manifest_path
        ),
        qsts_stratified_memo_path=(
            None if qsts_outputs is None else qsts_outputs.investment_memo_path
        ),
        full_year_selection_csv_path=full_year_selection_csv,
        qsts_full_year_results_csv_path=(
            None if qsts_full_year_outputs is None else qsts_full_year_outputs.results_csv_path
        ),
        qsts_full_year_summary_path=(
            None if qsts_full_year_outputs is None else qsts_full_year_outputs.summary_path
        ),
        qsts_full_year_manifest_path=(
            None if qsts_full_year_outputs is None else qsts_full_year_outputs.run_manifest_path
        ),
        qsts_full_year_memo_path=(
            None if qsts_full_year_outputs is None else qsts_full_year_outputs.investment_memo_path
        ),
        validation_matrix_csv_path=(
            None if validation_outputs is None else validation_outputs.csv_path
        ),
        validation_matrix_markdown_path=(
            None if validation_outputs is None else validation_outputs.markdown_path
        ),
        resize_results_csv_path=None if resize_outputs is None else resize_outputs.csv_path,
        resize_summary_path=None if resize_outputs is None else resize_outputs.summary_path,
        investor_report_html_path=None if bundle_outputs is None else bundle_outputs.html_path,
        scorecard_path=None if bundle_outputs is None else bundle_outputs.scorecard_path,
        campaign_guide_path=None if bundle_outputs is None else bundle_outputs.campaign_guide_path,
    )
    evidence = evidence_profile(
        evidence_level=_pipeline_evidence_level(qsts_outputs, qsts_full_year_outputs),
        data_source_type=request.data_source_type,
    )
    bess = request.bess_lite()
    report_path.write_text(
        render_pipeline_report(
            request,
            screening_result.rows,
            stratified_candidates,
            evidence,
            bess,
            full_year_candidates,
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(_pipeline_manifest(request, result, evidence, bess), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return result


def render_pipeline_report(
    request: PipelineRequest,
    screening_rows: tuple[object, ...],
    stratified_candidates: tuple[StratifiedCandidate, ...],
    evidence: EvidenceProfile,
    bess: BessLiteAssumptions,
    full_year_candidates: tuple[FullYearCandidate, ...] = (),
) -> str:
    best = screening_rows[0] if screening_rows else None
    best_bus = (
        f"{best.bus_id} ({best.bus_name}) verdict={best.verdict} "
        f"firm={best.firm_capacity_mw:.3f} MW conditional={best.conditional_capacity_mw:.3f} MW"
        if best is not None
        else "none"
    )
    return f"""# Thesegrid Pipeline Report

This report summarizes the first pipeline tranche for BESS flexible-connection
pre-feasibility. It is a buyer-side decision aid and does not replace an official
grid-connection study.

## Executive Summary

- evaluated_buses: {len(screening_rows)}
- stratified_shortlist_size: {len(stratified_candidates)}
- best_screening_bus: {best_bus}
- current_evidence_level: {evidence.evidence_level}
- decision_confidence: {evidence.decision_confidence}
- recommended_next_action: {evidence.recommended_next_action}

## Request

- network_code: {request.network_code}
- requested_mw: {request.requested_mw:.3f}
- asset: {request.asset}
- candidate_policy: {request.candidate_policy}

## BESS-Lite Assumptions

- power_mw: {bess.power_mw:.3f}
- duration_hours: {bess.duration_hours:.3f}
- nominal_energy_mwh: {bess.nominal_energy_mwh:.3f}
- round_trip_efficiency: {bess.round_trip_efficiency:.3f}
- soc_min_fraction: {bess.soc_min_fraction:.3f}
- soc_max_fraction: {bess.soc_max_fraction:.3f}
- usable_energy_mwh: {bess.usable_energy_mwh:.3f}
- efficiency_adjusted_usable_energy_mwh: {bess.efficiency_adjusted_usable_energy_mwh:.3f}

This is not a dispatch, degradation, revenue-stacking, or bankable valuation model.

## Evidence Boundary

- data_source_type: {evidence.data_source_type}
- evidence_level: {evidence.evidence_level}
- decision_confidence: {evidence.decision_confidence}
- recommended_next_action: {evidence.recommended_next_action}
- commercial_use: {evidence.commercial_use}

## Stage Status

| stage | status | primary_output |
| --- | --- | --- |
| screening | completed | screening/screening.csv |
| stratified_candidate_selection | completed | stratified_candidate_selection.csv |
| qsts_stratified | {_qsts_stage_status(request)} | {_qsts_stage_output(request)} |
| full_year_candidate_selection | {_full_year_selection_status(request)} | {_full_year_selection_output(request)} |
| qsts_full_year | {_qsts_full_year_stage_status(request)} | {_qsts_full_year_stage_output(request)} |
| validation_matrix | {_validation_matrix_stage_status(request)} | {_validation_matrix_stage_output(request)} |
| resize | {_resize_stage_status(request)} | {_resize_stage_output(request)} |
| investor_bundle | {_investor_bundle_stage_status(request)} | {_investor_bundle_stage_output(request)} |

{_qsts_stage_note(request)}

## Verdict Distribution

| verdict | count |
| --- | ---: |
{_verdict_distribution_table(screening_rows)}

## Top Screening Rows

| rank | bus_id | bus_name | verdict | firm_mw | conditional_mw |
| ---: | ---: | --- | --- | ---: | ---: |
{_top_screening_table(screening_rows, request.top_n)}

## Stratified QSTS Candidate Shortlist

| bus_id | bus_name | bucket | screening_verdict | reason |
| ---: | --- | --- | --- | --- |
{_stratified_candidate_table(stratified_candidates)}

## Full-Year Candidate Selection

| bus_id | bus_name | bucket | requested_mw |
| ---: | --- | --- | ---: |
{_full_year_candidate_table(full_year_candidates)}

## Artifact Index

| artifact | purpose |
| --- | --- |
| pipeline_report.md | Human-readable pipeline summary |
| pipeline_manifest.json | Reproducibility record for the pipeline tranche |
| screening/screening.csv | Ranked static screening rows |
| screening/screening_summary.md | Human-readable static screening summary |
| stratified_candidate_selection.csv | Balanced candidate shortlist for QSTS |
{_qsts_artifact_rows(request)}
{_full_year_selection_artifact_rows(request)}
{_validation_matrix_artifact_rows(request)}
{_resize_artifact_rows(request)}
{_investor_bundle_artifact_rows(request)}

## Recommended Next Actions

1. Run stratified QSTS on `stratified_candidate_selection.csv`.
2. Select full-year finalists from stratified QSTS results.
3. Run full-year QSTS before investor-facing flexible-envelope claims.
4. Use a client, consultant, reconstructed public, or operator-validated model before
   commercial site decisions.

## Remaining Scientific Uncertainty

- Screening is a proxy layer and can produce false positives.
- QSTS validation is required before investor-grade flexible-envelope claims.
- SimBench benchmark evidence does not replace client, consultant, or operator-grade
  network models.
"""


def _top_screening_table(screening_rows: tuple[object, ...], top_n: int) -> str:
    rows = "\n".join(
        f"| {row.rank} | {row.bus_id} | {row.bus_name} | {row.verdict} | "
        f"{row.firm_capacity_mw:.3f} | {row.conditional_capacity_mw:.3f} |"
        for row in screening_rows[:top_n]
    )
    return rows or "| | | | | | |"


def _stratified_candidate_table(candidates: tuple[StratifiedCandidate, ...]) -> str:
    rows = "\n".join(
        f"| {candidate.bus_id} | {candidate.bus_name} | {candidate.selection_bucket} | "
        f"{candidate.screening_verdict} | {candidate.selection_reason} |"
        for candidate in candidates
    )
    return rows or "| | | | | |"


def _full_year_candidate_table(candidates: tuple[FullYearCandidate, ...]) -> str:
    rows = "\n".join(
        f"| {candidate.bus_id} | {candidate.bus_name} | {candidate.selection_bucket} | "
        f"{candidate.requested_mw:.3f} |"
        for candidate in candidates
    )
    return rows or "| | | | |"


def _verdict_distribution_table(screening_rows: tuple[object, ...]) -> str:
    counts = {"go": 0, "go-with-conditions": 0, "no-go": 0}
    for row in screening_rows:
        verdict = str(row.verdict)
        counts[verdict] = counts.get(verdict, 0) + 1
    return "\n".join(f"| {verdict} | {count} |" for verdict, count in counts.items())


def _qsts_stratified_request(
    request: PipelineRequest,
    screening_csv_path: Path,
    stratified_candidates: tuple[StratifiedCandidate, ...],
) -> QstsRequest:
    bus_ids = tuple(candidate.bus_id for candidate in stratified_candidates)
    return QstsRequest(
        network_code=request.network_code,
        screening_csv=screening_csv_path,
        requested_mw=request.requested_mw,
        top_n=max(1, len(bus_ids)),
        bus_ids=bus_ids,
        asset=request.asset,
        start_hour=request.qsts_start_hour,
        duration_hours=request.qsts_duration_hours,
        sample_every_n_hours=request.qsts_sample_every_n_hours,
        stratified_sample=True,
        progress_every_n_hours=request.qsts_progress_every_n_hours,
        p90_curtailment_tolerance_mw=request.qsts_p90_curtailment_tolerance_mw,
        expected_curtailment_tolerance_mwh=request.qsts_expected_curtailment_tolerance_mwh,
        storage_duration_hours=request.storage_duration_hours,
    )


def _qsts_full_year_request(
    request: PipelineRequest,
    screening_csv_path: Path,
    full_year_candidates: tuple[FullYearCandidate, ...],
) -> QstsRequest:
    bus_ids = tuple(candidate.bus_id for candidate in full_year_candidates)
    if not bus_ids:
        raise ValueError("run_qsts_full_year requires at least one full-year candidate")
    return QstsRequest(
        network_code=request.network_code,
        screening_csv=screening_csv_path,
        requested_mw=request.requested_mw,
        top_n=max(1, len(bus_ids)),
        bus_ids=bus_ids,
        asset=request.asset,
        start_hour=0,
        duration_hours=None,
        sample_every_n_hours=1,
        stratified_sample=False,
        progress_every_n_hours=request.qsts_progress_every_n_hours,
        p90_curtailment_tolerance_mw=request.qsts_p90_curtailment_tolerance_mw,
        expected_curtailment_tolerance_mwh=request.qsts_expected_curtailment_tolerance_mwh,
        storage_duration_hours=request.storage_duration_hours,
    )


def _pipeline_evidence_level(qsts_outputs: object | None, full_year_outputs: object | None) -> str:
    if full_year_outputs is not None:
        return "qsts_full_year"
    if qsts_outputs is not None:
        return "qsts_stratified"
    return "screening_only"


def _qsts_stage_status(request: PipelineRequest) -> str:
    return "completed" if request.run_qsts_stratified else "not_run"


def _qsts_stage_output(request: PipelineRequest) -> str:
    return "qsts_stratified/qsts_results.csv" if request.run_qsts_stratified else ""


def _qsts_full_year_stage_status(request: PipelineRequest) -> str:
    return "completed" if request.run_qsts_full_year else "not_run"


def _qsts_full_year_stage_output(request: PipelineRequest) -> str:
    return "qsts_full_year/qsts_results.csv" if request.run_qsts_full_year else ""


def _validation_matrix_stage_status(request: PipelineRequest) -> str:
    return "completed" if request.run_qsts_full_year else "not_run"


def _validation_matrix_stage_output(request: PipelineRequest) -> str:
    return "validation/validation_matrix.csv" if request.run_qsts_full_year else ""


def _investor_bundle_stage_status(request: PipelineRequest) -> str:
    return "completed" if request.run_qsts_full_year else "not_run"


def _investor_bundle_stage_output(request: PipelineRequest) -> str:
    return "investor_report.html" if request.run_qsts_full_year else ""


def _resize_stage_status(request: PipelineRequest) -> str:
    return "completed" if request.run_resize_on_no_go else "not_run"


def _resize_stage_output(request: PipelineRequest) -> str:
    return "resize/resize_results.csv" if request.run_resize_on_no_go else ""


def _qsts_stage_note(request: PipelineRequest) -> str:
    if request.run_qsts_stratified:
        return (
            "Stratified QSTS was run for the selected shortlist. Full-year QSTS remains "
            "required before investor-facing flexible-envelope claims."
        )
    return (
        "QSTS was not run in this pipeline tranche. The selected buses are the next "
        "candidates for sampled or stratified QSTS validation."
    )


def _qsts_artifact_rows(request: PipelineRequest) -> str:
    if not request.run_qsts_stratified:
        return ""
    return "\n".join(
        (
            "| qsts_stratified/qsts_results.csv | Stratified QSTS verdicts and risk metrics |",
            "| qsts_stratified/investment_memo.md | QSTS investor-facing memo |",
            "| qsts_stratified/run_manifest.json | QSTS reproducibility record |",
        )
    )


def _full_year_selection_status(request: PipelineRequest) -> str:
    return "completed" if request.run_qsts_stratified else "not_run"


def _full_year_selection_output(request: PipelineRequest) -> str:
    return "full_year_candidate_selection.csv" if request.run_qsts_stratified else ""


def _full_year_selection_artifact_rows(request: PipelineRequest) -> str:
    if not request.run_qsts_stratified:
        return ""
    return (
        "| full_year_candidate_selection.csv | Candidate shortlist for full-year QSTS |"
    )


def _validation_matrix_artifact_rows(request: PipelineRequest) -> str:
    if not request.run_qsts_full_year:
        return ""
    return "\n".join(
        (
            "| validation/validation_matrix.csv | Screening vs QSTS validation matrix |",
            "| validation/validation_matrix.md | Human-readable validation matrix |",
        )
    )


def _investor_bundle_artifact_rows(request: PipelineRequest) -> str:
    if not request.run_qsts_full_year:
        return ""
    return "\n".join(
        (
            "| investor_report.html | Investor evidence bundle report |",
            "| scorecard.md | MVP evidence scorecard |",
            "| next_calibration_campaign.md | Recommended next calibration campaign |",
        )
    )


def _resize_artifact_rows(request: PipelineRequest) -> str:
    if not request.run_resize_on_no_go:
        return ""
    return "\n".join(
        (
            "| resize/resize_results.csv | QSTS resize scenarios for first no-go finalist |",
            "| resize/resize_summary.md | Human-readable resize recommendation |",
        )
    )


def _pipeline_manifest(
    request: PipelineRequest,
    result: PipelineResult,
    evidence: EvidenceProfile,
    bess: BessLiteAssumptions,
) -> dict[str, object]:
    return {
        "schema_version": "thesegrid-pipeline-manifest-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "request": _json_ready(asdict(request)),
        "bess_lite": bess.to_dict(),
        "evidence": asdict(evidence),
        "stages": {
            "screening": {
                "status": "completed",
                "outputs": {
                    "screening_csv": _relative(result.screening_csv_path, result.output_dir),
                    "screening_summary": _relative(result.screening_summary_path, result.output_dir),
                },
            },
            "stratified_selection": {
                "status": "completed",
                "outputs": {
                    "stratified_selection_csv": _relative(
                        result.stratified_selection_csv_path,
                        result.output_dir,
                    )
                },
            },
            "qsts_stratified": _qsts_manifest_stage(result),
            "full_year_selection": _full_year_selection_manifest_stage(result),
            "qsts_full_year": _qsts_full_year_manifest_stage(result),
            "validation_matrix": _validation_matrix_manifest_stage(result),
            "resize": _resize_manifest_stage(result),
            "investor_bundle": _investor_bundle_manifest_stage(result),
        },
        "outputs": {
            "pipeline_report": _relative(result.report_path, result.output_dir),
            "pipeline_manifest": _relative(result.manifest_path, result.output_dir),
        },
    }


def _qsts_manifest_stage(result: PipelineResult) -> dict[str, object]:
    if result.qsts_stratified_results_csv_path is None:
        return {"status": "not_run", "outputs": {}}
    return {
        "status": "completed",
        "outputs": {
            "qsts_results": _relative(result.qsts_stratified_results_csv_path, result.output_dir),
            "qsts_summary": _relative(result.qsts_stratified_summary_path, result.output_dir),
            "run_manifest": _relative(result.qsts_stratified_manifest_path, result.output_dir),
            "investment_memo": _relative(result.qsts_stratified_memo_path, result.output_dir),
        },
    }


def _full_year_selection_manifest_stage(result: PipelineResult) -> dict[str, object]:
    if result.full_year_selection_csv_path is None:
        return {"status": "not_run", "outputs": {}}
    return {
        "status": "completed",
        "outputs": {
            "full_year_candidate_selection": _relative(
                result.full_year_selection_csv_path,
                result.output_dir,
            )
        },
    }


def _qsts_full_year_manifest_stage(result: PipelineResult) -> dict[str, object]:
    if result.qsts_full_year_results_csv_path is None:
        return {"status": "not_run", "outputs": {}}
    return {
        "status": "completed",
        "outputs": {
            "qsts_results": _relative(result.qsts_full_year_results_csv_path, result.output_dir),
            "qsts_summary": _relative(result.qsts_full_year_summary_path, result.output_dir),
            "run_manifest": _relative(result.qsts_full_year_manifest_path, result.output_dir),
            "investment_memo": _relative(result.qsts_full_year_memo_path, result.output_dir),
        },
    }


def _validation_matrix_manifest_stage(result: PipelineResult) -> dict[str, object]:
    if result.validation_matrix_csv_path is None:
        return {"status": "not_run", "outputs": {}}
    return {
        "status": "completed",
        "outputs": {
            "validation_matrix_csv": _relative(
                result.validation_matrix_csv_path,
                result.output_dir,
            ),
            "validation_matrix_markdown": _relative(
                result.validation_matrix_markdown_path,
                result.output_dir,
            ),
        },
    }


def _investor_bundle_manifest_stage(result: PipelineResult) -> dict[str, object]:
    if result.investor_report_html_path is None:
        return {"status": "not_run", "outputs": {}}
    return {
        "status": "completed",
        "outputs": {
            "investor_report": _relative(result.investor_report_html_path, result.output_dir),
            "scorecard": _relative(result.scorecard_path, result.output_dir),
            "next_calibration_campaign": _relative(result.campaign_guide_path, result.output_dir),
        },
    }


def _resize_manifest_stage(result: PipelineResult) -> dict[str, object]:
    if result.resize_results_csv_path is None:
        return {"status": "not_run", "outputs": {}}
    return {
        "status": "completed",
        "outputs": {
            "resize_results": _relative(result.resize_results_csv_path, result.output_dir),
            "resize_summary": _relative(result.resize_summary_path, result.output_dir),
        },
    }


def _prepare_bundle_inputs(
    output_dir: Path,
    validation_outputs: object,
    qsts_outputs: object,
) -> None:
    _copy_if_available(
        getattr(validation_outputs, "csv_path", None),
        output_dir / "validation_matrix.csv",
    )
    _copy_if_available(
        getattr(validation_outputs, "markdown_path", None),
        output_dir / "validation_matrix.md",
    )
    _copy_qsts_artifact(qsts_outputs, "results_csv_path", output_dir / "qsts_results.csv")
    _copy_qsts_artifact(qsts_outputs, "performance_json_path", output_dir / "qsts_performance.json")
    _copy_qsts_artifact(qsts_outputs, "decision_frontier_csv_path", output_dir / "decision_frontier.csv")
    _copy_qsts_artifact(qsts_outputs, "risk_summary_csv_path", output_dir / "qsts_risk_summary.csv")
    _copy_qsts_artifact(qsts_outputs, "economics_csv_path", output_dir / "qsts_economics.csv")
    _copy_qsts_artifact(
        qsts_outputs,
        "static_vs_qsts_comparison_csv_path",
        output_dir / "static_vs_qsts_comparison.csv",
    )
    _copy_qsts_artifact(
        qsts_outputs,
        "contractual_envelope_csv_path",
        output_dir / "contractual_envelope.csv",
    )
    _copy_qsts_artifact(qsts_outputs, "run_manifest_path", output_dir / "run_manifest.json")
    _copy_qsts_artifact(qsts_outputs, "investment_memo_path", output_dir / "investment_memo.md")


def _copy_qsts_artifact(qsts_outputs: object, attribute_name: str, destination: Path) -> None:
    _copy_if_available(getattr(qsts_outputs, attribute_name, None), destination)


def _copy_if_available(source: object, destination: Path) -> None:
    if not isinstance(source, Path) or not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == destination.resolve():
        return
    copyfile(source, destination)


def _existing_output_paths(outputs: object, attribute_name: str) -> tuple[Path, ...]:
    path = getattr(outputs, attribute_name, None)
    if isinstance(path, Path) and path.exists():
        return (path,)
    return ()


def _relative(path: Path, base: Path) -> str:
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
