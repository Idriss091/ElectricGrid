from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from thesegrid.assessment import assess_connection
from thesegrid.bundle import write_bundle_report
from thesegrid.constraints import ConstraintSettings
from thesegrid.full_year_selection import (
    FullYearSelectionRequest,
    select_full_year_candidates,
    write_full_year_selection_csv,
)
from thesegrid.memo import write_investment_memo
from thesegrid.models import ConnectionRequest, EconomicAssumptions
from thesegrid.qsts import (
    QstsRequest,
    _decision_confidence,
    _qsts_economics_proxy,
    _qsts_verdict_driver,
    _recommended_next_action,
    _validation_level,
    run_qsts,
    write_qsts_outputs,
)
from thesegrid.screening import ScreeningRequest, screen_connections, write_screening_outputs
from thesegrid.validation_matrix import build_validation_matrix, write_validation_matrix_outputs


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args._argv = tuple(sys.argv[1:] if argv is None else argv)
    if args.command == "assess":
        return _assess(args)
    if args.command == "screen":
        return _screen(args)
    if args.command == "qsts":
        return _qsts(args)
    if args.command == "qsts-resize":
        return _qsts_resize(args)
    if args.command == "qsts-sweep":
        return _qsts_sweep(args)
    if args.command == "compare-validation":
        return _compare_validation(args)
    if args.command == "select-full-year-candidates":
        return _select_full_year_candidates(args)
    if args.command == "render-bundle":
        return _render_bundle(args)
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thesegrid")
    subparsers = parser.add_subparsers(dest="command")

    assess = subparsers.add_parser("assess", help="Run BESS connection pre-feasibility")
    assess.add_argument("--network", required=True, help="SimBench code, or 'toy' for smoke tests")
    assess.add_argument("--bus", required=True, type=int, help="Candidate connection bus id")
    assess.add_argument("--requested-mw", required=True, type=float, help="Requested BESS MW")
    assess.add_argument("--asset", default="bess", help="Asset type; V1 supports only 'bess'")
    assess.add_argument("--output", type=Path, help="Output memo path")
    assess.add_argument(
        "--curtailment-tolerance-mwh",
        type=float,
        default=0.0,
        help="Annual curtailment tolerance in MWh",
    )
    assess.add_argument(
        "--p90-curtailment-tolerance-mw",
        type=float,
        default=0.0,
        help="P90 hourly curtailment tolerance in MW",
    )
    assess.add_argument("--reinforcement-wait-years", type=float, default=5.0)
    assess.add_argument("--gross-margin-eur-per-mwh", type=float, default=0.0)
    assess.add_argument("--curtailment-penalty-eur-per-mwh", type=float, default=100.0)
    assess.add_argument("--waiting-cost-eur-per-mw-year", type=float, default=50_000.0)
    screen = subparsers.add_parser("screen", help="Rank candidate BESS connection buses")
    screen.add_argument("--network", required=True, help="SimBench code, or 'toy' for smoke tests")
    screen.add_argument("--requested-mw", required=True, type=float, help="Requested BESS MW")
    screen.add_argument("--asset", default="bess", help="Asset type; V1 supports only 'bess'")
    screen.add_argument("--output", type=Path, required=True, help="Output directory")
    screen.add_argument("--top-n", type=int, default=10, help="Rows to show in Markdown summary")
    screen.add_argument(
        "--max-buses",
        type=int,
        help="Maximum number of candidate buses to evaluate before ranking",
    )
    screen.add_argument(
        "--candidate-policy",
        default="mv_active",
        choices=["mv_active"],
        help="Candidate bus selection policy",
    )
    screen.add_argument(
        "--curtailment-tolerance-mwh",
        type=float,
        default=0.0,
        help="Annual curtailment tolerance in MWh",
    )
    screen.add_argument(
        "--p90-curtailment-tolerance-mw",
        type=float,
        default=0.0,
        help="P90 hourly curtailment tolerance in MW",
    )
    screen.add_argument("--reinforcement-wait-years", type=float, default=5.0)
    screen.add_argument("--gross-margin-eur-per-mwh", type=float, default=0.0)
    screen.add_argument("--curtailment-penalty-eur-per-mwh", type=float, default=100.0)
    screen.add_argument("--waiting-cost-eur-per-mw-year", type=float, default=50_000.0)
    qsts = subparsers.add_parser("qsts", help="Validate top screened buses with QSTS")
    qsts.add_argument("--network", required=True, help="SimBench code; 'toy' is refused for QSTS")
    qsts.add_argument("--screening-csv", required=True, type=Path, help="Input screening.csv path")
    qsts.add_argument("--requested-mw", required=True, type=float, help="Requested BESS MW")
    qsts.add_argument("--output", type=Path, required=True, help="Output directory")
    qsts.add_argument("--top-n", type=int, default=10, help="Top screening rows to validate")
    qsts.add_argument(
        "--bus-ids",
        help="Comma-separated screening bus IDs to validate; overrides --top-n selection",
    )
    qsts.add_argument("--asset", default="bess", help="Asset type; V1 supports only 'bess'")
    qsts.add_argument("--start-hour", type=int, default=0, help="First hourly profile index to validate")
    qsts.add_argument("--duration-hours", type=int, help="Number of hourly profile steps to validate")
    qsts.add_argument(
        "--sample-every-n-hours",
        type=int,
        default=1,
        help="Evaluate every Nth hourly profile step",
    )
    qsts.add_argument(
        "--stratified-sample",
        action="store_true",
        help="Select one representative hour per month and V1 time block",
    )
    qsts.add_argument(
        "--voltage-min-pu",
        type=float,
        default=0.95,
        help="Minimum accepted bus voltage in per unit",
    )
    qsts.add_argument(
        "--voltage-max-pu",
        type=float,
        default=1.05,
        help="Maximum accepted bus voltage in per unit",
    )
    qsts.add_argument(
        "--max-loading-percent",
        type=float,
        default=100.0,
        help="Maximum accepted line/trafo loading percent",
    )
    qsts.add_argument(
        "--p90-curtailment-tolerance-mw",
        type=float,
        default=0.0,
        help="Accepted QSTS P90 hourly curtailment in MW for go-with-conditions",
    )
    qsts.add_argument(
        "--expected-curtailment-tolerance-mwh",
        type=float,
        default=0.0,
        help="Accepted QSTS expected curtailed MWh for go-with-conditions",
    )
    qsts.add_argument(
        "--progress-every-n-hours",
        type=int,
        default=250,
        help="Print compact QSTS progress every N evaluated bus-hours; 0 disables progress",
    )
    qsts.add_argument("--storage-duration-hours", type=float, default=4.0)
    qsts.add_argument("--capex-eur-per-kw", type=float, default=0.0)
    qsts.add_argument("--fixed-opex-eur-per-kw-year", type=float, default=0.0)
    qsts.add_argument("--gross-revenue-eur-per-mw-year", type=float, default=0.0)
    qsts.add_argument("--curtailment-penalty-eur-per-mwh", type=float, default=100.0)
    qsts.add_argument("--reinforcement-wait-years", type=float, default=5.0)
    qsts.add_argument("--discount-rate", type=float, default=0.08)
    resize = subparsers.add_parser(
        "qsts-resize",
        help="Find the largest QSTS-acceptable resized MW for one bus",
    )
    resize.add_argument("--network", required=True, help="SimBench code; 'toy' is refused for QSTS")
    resize.add_argument("--screening-csv", required=True, type=Path, help="Input screening.csv path")
    resize.add_argument("--bus-id", required=True, type=int, help="Candidate bus id to resize")
    resize.add_argument("--requested-mw", required=True, type=float, help="Original requested BESS MW")
    resize.add_argument("--min-mw", required=True, type=float, help="Smallest MW to test")
    resize.add_argument("--step-mw", type=float, default=1.0, help="Descending MW step")
    resize.add_argument("--output", required=True, type=Path, help="Output directory")
    resize.add_argument("--asset", default="bess", help="Asset type; V1 supports only 'bess'")
    resize.add_argument("--start-hour", type=int, default=0)
    resize.add_argument("--duration-hours", type=int)
    resize.add_argument("--sample-every-n-hours", type=int, default=1)
    resize.add_argument("--stratified-sample", action="store_true")
    resize.add_argument("--voltage-min-pu", type=float, default=0.95)
    resize.add_argument("--voltage-max-pu", type=float, default=1.05)
    resize.add_argument("--max-loading-percent", type=float, default=100.0)
    resize.add_argument("--p90-curtailment-tolerance-mw", type=float, default=0.0)
    resize.add_argument("--expected-curtailment-tolerance-mwh", type=float, default=0.0)
    resize.add_argument("--progress-every-n-hours", type=int, default=250)
    resize.add_argument("--storage-duration-hours", type=float, default=4.0)
    resize.add_argument("--capex-eur-per-kw", type=float, default=0.0)
    resize.add_argument("--fixed-opex-eur-per-kw-year", type=float, default=0.0)
    resize.add_argument("--gross-revenue-eur-per-mw-year", type=float, default=0.0)
    resize.add_argument("--curtailment-penalty-eur-per-mwh", type=float, default=100.0)
    resize.add_argument("--reinforcement-wait-years", type=float, default=5.0)
    resize.add_argument("--discount-rate", type=float, default=0.08)
    sweep = subparsers.add_parser("qsts-sweep", help="Run a QSTS sensitivity sweep from JSON")
    sweep.add_argument("--config", required=True, type=Path, help="Sweep JSON config path")
    sweep.add_argument("--output", required=True, type=Path, help="Output directory")
    compare = subparsers.add_parser(
        "compare-validation",
        help="Compare screening, short QSTS, stratified QSTS, and full-year QSTS",
    )
    compare.add_argument("--screening-csv", required=True, type=Path, help="Input screening.csv path")
    compare.add_argument("--qsts-short", required=True, type=Path, help="Input 24h QSTS results CSV")
    compare.add_argument(
        "--qsts-stratified",
        required=True,
        type=Path,
        help="Input stratified QSTS results CSV",
    )
    compare.add_argument(
        "--qsts-full-year",
        required=True,
        type=Path,
        nargs="+",
        help="One or more full-year QSTS results CSV paths",
    )
    compare.add_argument("--output", required=True, type=Path, help="Output directory")
    select_full_year = subparsers.add_parser(
        "select-full-year-candidates",
        help="Select a balanced set of QSTS full-year candidates",
    )
    select_full_year.add_argument("--screening-csv", required=True, type=Path)
    select_full_year.add_argument("--stratified-csv", type=Path)
    select_full_year.add_argument("--validation-matrix-csv", type=Path)
    select_full_year.add_argument("--output", required=True, type=Path)
    select_full_year.add_argument("--max-candidates", type=int, default=8)
    select_full_year.add_argument("--top-candidates", type=int, default=3)
    select_full_year.add_argument("--borderline-candidates", type=int, default=3)
    select_full_year.add_argument("--false-positive-suspects", type=int, default=1)
    select_full_year.add_argument("--bad-controls", type=int, default=1)
    bundle = subparsers.add_parser(
        "render-bundle",
        help="Render HTML report, scorecard, and next-campaign guide for an investor bundle",
    )
    bundle.add_argument("--bundle", required=True, type=Path, help="Investor bundle directory")
    return parser


def _assess(args: argparse.Namespace) -> int:
    request = ConnectionRequest(
        network_code=args.network,
        bus_id=args.bus,
        requested_mw=args.requested_mw,
        asset=args.asset,
        curtailment_tolerance_mwh_per_year=args.curtailment_tolerance_mwh,
        p90_curtailment_tolerance_mw=args.p90_curtailment_tolerance_mw,
        reinforcement_wait_years=args.reinforcement_wait_years,
        economics=EconomicAssumptions(
            gross_margin_eur_per_mwh=args.gross_margin_eur_per_mwh,
            curtailment_penalty_eur_per_mwh=args.curtailment_penalty_eur_per_mwh,
            waiting_cost_eur_per_mw_year=args.waiting_cost_eur_per_mw_year,
        ),
    )
    memo = assess_connection(request)
    output = args.output or _default_output_path(request)
    write_investment_memo(memo, output)
    print(f"{memo.verdict}: {output}")
    return 0


def _default_output_path(request: ConnectionRequest) -> Path:
    network = re.sub(r"[^A-Za-z0-9_.-]+", "-", request.network_code)
    requested = f"{request.requested_mw:.3f}".rstrip("0").rstrip(".")
    return Path("results") / f"{network}_bus-{request.bus_id}_{requested}mw" / "memo.md"


def _screen(args: argparse.Namespace) -> int:
    request = ScreeningRequest(
        network_code=args.network,
        requested_mw=args.requested_mw,
        asset=args.asset,
        top_n=args.top_n,
        max_buses=args.max_buses,
        candidate_policy=args.candidate_policy,
        curtailment_tolerance_mwh_per_year=args.curtailment_tolerance_mwh,
        p90_curtailment_tolerance_mw=args.p90_curtailment_tolerance_mw,
        reinforcement_wait_years=args.reinforcement_wait_years,
        economics=EconomicAssumptions(
            gross_margin_eur_per_mwh=args.gross_margin_eur_per_mwh,
            curtailment_penalty_eur_per_mwh=args.curtailment_penalty_eur_per_mwh,
            waiting_cost_eur_per_mw_year=args.waiting_cost_eur_per_mw_year,
        ),
    )
    limit = f" up to {request.max_buses}" if request.max_buses is not None else ""
    print(f"screening{limit} candidate buses...", file=sys.stderr)
    result = screen_connections(request)
    outputs = write_screening_outputs(result, args.output)
    print(f"screened {len(result.rows)} buses: {outputs.csv_path} {outputs.summary_path}")
    return 0


def _qsts(args: argparse.Namespace) -> int:
    try:
        request = QstsRequest(
            network_code=args.network,
            screening_csv=args.screening_csv,
            requested_mw=args.requested_mw,
            top_n=args.top_n,
            bus_ids=_parse_bus_ids(args.bus_ids),
            asset=args.asset,
            start_hour=args.start_hour,
            duration_hours=args.duration_hours,
            sample_every_n_hours=args.sample_every_n_hours,
            stratified_sample=args.stratified_sample,
            progress_every_n_hours=args.progress_every_n_hours,
            p90_curtailment_tolerance_mw=args.p90_curtailment_tolerance_mw,
            expected_curtailment_tolerance_mwh=args.expected_curtailment_tolerance_mwh,
            storage_duration_hours=args.storage_duration_hours,
            capex_eur_per_kw=args.capex_eur_per_kw,
            fixed_opex_eur_per_kw_year=args.fixed_opex_eur_per_kw_year,
            gross_revenue_eur_per_mw_year=args.gross_revenue_eur_per_mw_year,
            curtailment_penalty_eur_per_mwh=args.curtailment_penalty_eur_per_mwh,
            reinforcement_wait_years=args.reinforcement_wait_years,
            discount_rate=args.discount_rate,
        )
        settings = ConstraintSettings(
            min_vm_pu=args.voltage_min_pu,
            max_vm_pu=args.voltage_max_pu,
            max_loading_percent=args.max_loading_percent,
        )
        if request.bus_ids:
            print(f"validating {len(request.bus_ids)} forced buses with QSTS...", file=sys.stderr)
        else:
            print(f"validating top {request.top_n} buses with QSTS...", file=sys.stderr)
        result = run_qsts(request, settings=settings)
    except (ImportError, ValueError) as exc:
        print(f"qsts error: {exc}")
        return 2
    outputs = write_qsts_outputs(result, args.output, command=args._argv)
    print(f"qsts validated {len(result.buses)} buses: {outputs.results_csv_path} {outputs.summary_path}")
    return 0


def _qsts_resize(args: argparse.Namespace) -> int:
    try:
        mw_values = _resize_mw_values(args.requested_mw, args.min_mw, args.step_mw)
        settings = ConstraintSettings(
            min_vm_pu=args.voltage_min_pu,
            max_vm_pu=args.voltage_max_pu,
            max_loading_percent=args.max_loading_percent,
        )
        args.output.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, object]] = []
        for index, requested_mw in enumerate(mw_values, start=1):
            scenario_id = f"mw_{_slug_mw(requested_mw)}"
            scenario_dir = args.output / scenario_id
            request = QstsRequest(
                network_code=args.network,
                screening_csv=args.screening_csv,
                requested_mw=requested_mw,
                top_n=1,
                bus_ids=(args.bus_id,),
                asset=args.asset,
                start_hour=args.start_hour,
                duration_hours=args.duration_hours,
                sample_every_n_hours=args.sample_every_n_hours,
                stratified_sample=args.stratified_sample,
                progress_every_n_hours=args.progress_every_n_hours,
                p90_curtailment_tolerance_mw=args.p90_curtailment_tolerance_mw,
                expected_curtailment_tolerance_mwh=args.expected_curtailment_tolerance_mwh,
                storage_duration_hours=args.storage_duration_hours,
                capex_eur_per_kw=args.capex_eur_per_kw,
                fixed_opex_eur_per_kw_year=args.fixed_opex_eur_per_kw_year,
                gross_revenue_eur_per_mw_year=args.gross_revenue_eur_per_mw_year,
                curtailment_penalty_eur_per_mwh=args.curtailment_penalty_eur_per_mwh,
                reinforcement_wait_years=args.reinforcement_wait_years,
                discount_rate=args.discount_rate,
            )
            print(
                f"qsts-resize validating bus {args.bus_id} at {requested_mw:.3f} MW "
                f"({index}/{len(mw_values)})...",
                file=sys.stderr,
            )
            result = run_qsts(request, settings=settings)
            write_qsts_outputs(
                result,
                scenario_dir,
                command=(
                    "qsts-resize",
                    "--requested-mw",
                    f"{requested_mw:.6f}",
                    "--scenario",
                    scenario_id,
                ),
            )
            rows.append(_resize_result_row(result, scenario_dir, args.requested_mw))
    except (ImportError, ValueError) as exc:
        print(f"qsts-resize error: {exc}")
        return 2

    results_csv = args.output / "resize_results.csv"
    _write_resize_results(results_csv, rows)
    summary_path = args.output / "resize_summary.md"
    summary_path.write_text(
        _render_resize_summary(
            rows=rows,
            bus_id=args.bus_id,
            original_requested_mw=args.requested_mw,
        ),
        encoding="utf-8",
    )
    print(f"qsts-resize completed {len(rows)} scenarios: {results_csv} {summary_path}")
    return 0


def _qsts_sweep(args: argparse.Namespace) -> int:
    try:
        config = _load_sweep_config(args.config)
        scenarios = _sweep_scenarios(config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"qsts-sweep error: {exc}")
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    calibration_rows: list[dict[str, object]] = []
    for index, scenario in enumerate(scenarios, start=1):
        scenario_id = f"scenario_{index:03d}"
        scenario_dir = args.output / scenario_id
        sampling_mode = str(scenario["sampling_mode"])
        request = QstsRequest(
            network_code=str(config["network_code"]),
            screening_csv=Path(config["screening_csv"]),
            requested_mw=float(scenario["requested_mw"]),
            top_n=int(config.get("top_n", 3)),
            bus_ids=_config_bus_ids(config),
            start_hour=int(config.get("start_hour", 0)),
            duration_hours=(
                int(config["duration_hours"]) if config.get("duration_hours") is not None else None
            ),
            sample_every_n_hours=int(config.get("sample_every_n_hours", 1)),
            stratified_sample=sampling_mode == "stratified",
            p90_curtailment_tolerance_mw=float(scenario["p90_curtailment_tolerance_mw"]),
            expected_curtailment_tolerance_mwh=float(
                scenario["expected_curtailment_tolerance_mwh"]
            ),
            progress_every_n_hours=int(config.get("progress_every_n_hours", 0)),
        )
        settings = ConstraintSettings(max_vm_pu=float(scenario["voltage_max_pu"]))
        result = run_qsts(request, settings=settings)
        write_qsts_outputs(
            result,
            scenario_dir,
            command=("qsts-sweep", "--config", str(args.config), "--scenario", scenario_id),
        )
        rows.extend(_sweep_result_rows(scenario_id, scenario, result))
        calibration_rows.extend(_sampling_calibration_rows(scenario_id, scenario, result))

    results_csv = args.output / "sensitivity_results.csv"
    _write_sensitivity_results(results_csv, rows)
    calibration_csv = args.output / "sampling_calibration.csv"
    _write_sampling_calibration(calibration_csv, calibration_rows)
    summary_path = args.output / "sensitivity_summary.md"
    summary_path.write_text(_render_sensitivity_summary(rows), encoding="utf-8")
    manifest_path = args.output / "sweep_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "qsts-sweep-manifest-v1",
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "config": config,
                "scenario_count": len(scenarios),
                "outputs": {
                    "sensitivity_results": "sensitivity_results.csv",
                    "sensitivity_summary": "sensitivity_summary.md",
                    "sampling_calibration": "sampling_calibration.csv",
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"qsts-sweep completed {len(scenarios)} scenarios: {results_csv} {summary_path}")
    return 0


def _compare_validation(args: argparse.Namespace) -> int:
    matrix = build_validation_matrix(
        screening_csv=args.screening_csv,
        qsts_short_csv=args.qsts_short,
        qsts_stratified_csv=args.qsts_stratified,
        qsts_full_year_csvs=tuple(args.qsts_full_year),
    )
    outputs = write_validation_matrix_outputs(matrix, args.output)
    print(f"validation matrix: {outputs.csv_path} {outputs.markdown_path}")
    return 0


def _select_full_year_candidates(args: argparse.Namespace) -> int:
    candidates = select_full_year_candidates(
        FullYearSelectionRequest(
            screening_csv=args.screening_csv,
            stratified_csv=args.stratified_csv,
            validation_matrix_csv=args.validation_matrix_csv,
            max_candidates=args.max_candidates,
            top_candidates=args.top_candidates,
            borderline_candidates=args.borderline_candidates,
            false_positive_suspects=args.false_positive_suspects,
            bad_controls=args.bad_controls,
        )
    )
    output = write_full_year_selection_csv(candidates, args.output)
    print(f"full-year candidate selection: {output}")
    return 0


def _render_bundle(args: argparse.Namespace) -> int:
    outputs = write_bundle_report(args.bundle)
    print(
        "bundle report: "
        f"{outputs.html_path} {outputs.scorecard_path} {outputs.campaign_guide_path}"
    )
    return 0


def _load_sweep_config(path: Path) -> dict[str, object]:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = (
        "network_code",
        "screening_csv",
        "requested_mw",
        "p90_curtailment_tolerance_mw",
        "expected_curtailment_tolerance_mwh",
        "voltage_max_pu",
    )
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"missing required sweep config keys: {', '.join(missing)}")
    for key in required[2:]:
        if not isinstance(config[key], list) or not config[key]:
            raise ValueError(f"{key} must be a non-empty list")
    if "sampling_modes" in config:
        if not isinstance(config["sampling_modes"], list) or not config["sampling_modes"]:
            raise ValueError("sampling_modes must be a non-empty list")
        invalid = [
            mode
            for mode in config["sampling_modes"]
            if mode not in {"stratified", "full_year"}
        ]
        if invalid:
            raise ValueError("sampling_modes values must be 'stratified' or 'full_year'")
    elif config.get("sampling", "stratified") not in {"stratified", "full_year"}:
        raise ValueError("sampling must be 'stratified' or 'full_year'")
    if "bus_ids" in config:
        if not isinstance(config["bus_ids"], list) or not config["bus_ids"]:
            raise ValueError("bus_ids must be a non-empty list")
        for bus_id in config["bus_ids"]:
            if int(bus_id) < 0:
                raise ValueError("bus_ids must be non-negative")
    return config


def _sweep_scenarios(config: dict[str, object]) -> list[dict[str, object]]:
    keys = (
        "requested_mw",
        "p90_curtailment_tolerance_mw",
        "expected_curtailment_tolerance_mwh",
        "voltage_max_pu",
    )
    scenarios: list[dict[str, object]] = []
    sampling_modes = config.get("sampling_modes", [config.get("sampling", "stratified")])
    for values in itertools.product(*(config[key] for key in keys), sampling_modes):
        numeric_values = values[:-1]
        sampling_mode = values[-1]
        scenario = {key: float(value) for key, value in zip(keys, numeric_values)}
        scenario["sampling_mode"] = str(sampling_mode)
        scenarios.append(scenario)
    return scenarios


def _sweep_result_rows(
    scenario_id: str,
    scenario: dict[str, object],
    result,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for bus in result.buses:
        rows.append(
            {
                "scenario_id": scenario_id,
                "bus_id": bus.bus_id,
                "bus_name": bus.bus_name,
                "qsts_verdict": bus.qsts_verdict,
                "sampling_mode": scenario["sampling_mode"],
                "requested_mw": f"{float(scenario['requested_mw']):.6f}",
                "p90_curtailment_tolerance_mw": f"{float(scenario['p90_curtailment_tolerance_mw']):.6f}",
                "expected_curtailment_tolerance_mwh": (
                    f"{float(scenario['expected_curtailment_tolerance_mwh']):.6f}"
                ),
                "voltage_max_pu": f"{float(scenario['voltage_max_pu']):.6f}",
                "static_firm_capacity_mw": f"{bus.static_firm_capacity_mw:.6f}",
                "static_conditional_capacity_mw": f"{bus.static_conditional_capacity_mw:.6f}",
                "qsts_p90_curtailment_mw": f"{bus.curtailment.p90_mw:.6f}",
                "qsts_expected_curtailment_mwh": f"{bus.curtailment.expected_mwh:.6f}",
                "main_recurring_constraint": bus.main_recurring_constraint,
            }
        )
    return rows


def _write_sensitivity_results(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "scenario_id",
        "bus_id",
        "bus_name",
        "qsts_verdict",
        "sampling_mode",
        "requested_mw",
        "p90_curtailment_tolerance_mw",
        "expected_curtailment_tolerance_mwh",
        "voltage_max_pu",
        "static_firm_capacity_mw",
        "static_conditional_capacity_mw",
        "qsts_p90_curtailment_mw",
        "qsts_expected_curtailment_mwh",
        "main_recurring_constraint",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_sensitivity_summary(rows: list[dict[str, object]]) -> str:
    if not rows:
        table = "No QSTS sweep rows available."
    else:
        lines = [
            "| scenario | sampling | bus_id | verdict | requested_mw | p90_tol_mw | mwh_tol | voltage_max_pu | qsts_p90_mw | qsts_mwh |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in rows:
            lines.append(
                "| "
                f"{row['scenario_id']} | {row['sampling_mode']} | "
                f"{row['bus_id']} | {row['qsts_verdict']} | "
                f"{row['requested_mw']} | {row['p90_curtailment_tolerance_mw']} | "
                f"{row['expected_curtailment_tolerance_mwh']} | {row['voltage_max_pu']} | "
                f"{row['qsts_p90_curtailment_mw']} | {row['qsts_expected_curtailment_mwh']} |"
            )
        table = "\n".join(lines)
    return f"""# QSTS Sensitivity Summary

{table}
"""


def _sampling_calibration_rows(
    scenario_id: str,
    scenario: dict[str, object],
    result,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for bus in result.buses:
        rows.append(
            {
                "scenario_id": scenario_id,
                "sampling_mode": scenario["sampling_mode"],
                "bus_id": bus.bus_id,
                "qsts_verdict": bus.qsts_verdict,
                "evaluated_hours": result.performance.evaluated_time_steps,
                "expected_mwh": f"{bus.curtailment.expected_mwh:.6f}",
                "p90_mw": f"{bus.curtailment.p90_mw:.6f}",
                "runtime_seconds": f"{result.performance.runtime_seconds:.6f}",
            }
        )
    return rows


def _write_sampling_calibration(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "scenario_id",
        "sampling_mode",
        "bus_id",
        "qsts_verdict",
        "evaluated_hours",
        "expected_mwh",
        "p90_mw",
        "runtime_seconds",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _resize_mw_values(requested_mw: float, min_mw: float, step_mw: float) -> list[float]:
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


def _resize_result_row(result, scenario_dir: Path, original_requested_mw: float) -> dict[str, object]:
    if not result.buses:
        raise ValueError("qsts-resize scenario returned no bus results")
    bus = result.buses[0]
    driver = _qsts_verdict_driver(
        bus.curtailment,
        p90_tolerance_mw=result.request.p90_curtailment_tolerance_mw,
        mwh_tolerance=result.request.expected_curtailment_tolerance_mwh,
    )
    economics = _qsts_economics_proxy(result)
    product_decision = _resize_product_decision(
        bus.qsts_verdict,
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
        "product_decision": product_decision,
        "acceptable": str(_resize_acceptable(bus.qsts_verdict)),
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


def _resize_acceptable(qsts_verdict: str) -> bool:
    return qsts_verdict in {"go", "go-with-conditions"}


def _resize_product_decision(
    qsts_verdict: str,
    requested_mw: float,
    original_requested_mw: float,
) -> str:
    if not _resize_acceptable(qsts_verdict):
        return "no-go"
    if requested_mw < original_requested_mw - 1e-9:
        return "resize-recommended"
    return qsts_verdict


def _write_resize_results(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "requested_mw",
        "original_requested_mw",
        "delta_mw_from_original",
        "bus_id",
        "bus_name",
        "qsts_verdict",
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
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_resize_summary(
    rows: list[dict[str, object]],
    bus_id: int,
    original_requested_mw: float,
) -> str:
    recommended = _recommended_resize_row(rows)
    if recommended is None:
        recommendation = (
            f"Bus {bus_id} is not acceptable at {original_requested_mw:.3f} MW and no "
            "tested lower MW met the configured QSTS tolerances."
        )
        recommended_line = "- recommended_resized_mw: none"
    else:
        recommended_mw = float(str(recommended["requested_mw"]))
        delta_mw = float(str(recommended["delta_mw_from_original"]))
        recommendation = (
            f"Bus {bus_id} is not acceptable at {original_requested_mw:.3f} MW, but is "
            f"acceptable at {recommended_mw:.3f} MW with verdict "
            f"`{recommended['qsts_verdict']}`."
        )
        recommended_line = (
            f"- product_decision: {recommended['product_decision']}\n"
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

{_render_resize_table(rows)}
"""


def _recommended_resize_row(rows: list[dict[str, object]]) -> dict[str, object] | None:
    acceptable = [row for row in rows if row["acceptable"] == "True"]
    if not acceptable:
        return None
    return max(acceptable, key=lambda row: float(str(row["requested_mw"])))


def _render_resize_table(rows: list[dict[str, object]]) -> str:
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


def _slug_mw(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".").replace(".", "p")


def _parse_bus_ids(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    bus_ids: list[int] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        bus_ids.append(int(item))
    return tuple(bus_ids)


def _config_bus_ids(config: dict[str, object]) -> tuple[int, ...]:
    if "bus_ids" not in config:
        return ()
    return tuple(int(bus_id) for bus_id in config["bus_ids"])


if __name__ == "__main__":
    raise SystemExit(main())
