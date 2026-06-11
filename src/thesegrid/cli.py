from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from thesegrid.assessment import assess_connection
from thesegrid.bundle import write_bundle_report
from thesegrid.client_network import validate_client_network, write_client_network_validation
from thesegrid.commercial_reporting import run_commercial_validation
from thesegrid.commercial_validation import CommercialValidationError
from thesegrid.constraints import ConstraintSettings
from thesegrid.full_year_selection import (
    DEFAULT_FULL_YEAR_BAD_CONTROLS,
    DEFAULT_FULL_YEAR_BORDERLINE_CANDIDATES,
    DEFAULT_FULL_YEAR_FALSE_POSITIVE_SUSPECTS,
    DEFAULT_FULL_YEAR_MAX_CANDIDATES,
    DEFAULT_FULL_YEAR_TOP_CANDIDATES,
    FullYearSelectionRequest,
    select_full_year_candidates,
    write_full_year_selection_csv,
)
from thesegrid.memo import write_investment_memo
from thesegrid.models import ConnectionRequest, EconomicAssumptions
from thesegrid.pipeline import PipelineRequest, run_pipeline
from thesegrid.portfolio_workflow import PortfolioWorkflowRequest, run_portfolio_workflow
from thesegrid.qsts import QstsRequest, run_qsts, write_qsts_outputs
from thesegrid.resize import ResizeRequest, run_resize_scenarios, write_resize_outputs
from thesegrid.screening import ScreeningRequest, screen_connections, write_screening_outputs
from thesegrid.stratified_selection import (
    DEFAULT_STRATIFIED_BORDERLINE_CANDIDATES,
    DEFAULT_STRATIFIED_CONSTRAINT_DIVERSE_CANDIDATES,
    DEFAULT_STRATIFIED_MAX_CANDIDATES,
    DEFAULT_STRATIFIED_NEAR_THRESHOLD_NO_GO_CANDIDATES,
    DEFAULT_STRATIFIED_TOP_GO_CANDIDATES,
    StratifiedSelectionRequest,
    select_stratified_candidates,
    write_stratified_selection_csv,
)
from thesegrid.validation_matrix import build_validation_matrix, write_validation_matrix_outputs


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args._argv = tuple(sys.argv[1:] if argv is None else argv)
    if args.command == "assess":
        return _assess(args)
    if args.command == "screen":
        return _screen(args)
    if args.command == "portfolio-screen":
        return _portfolio_screen(args)
    if args.command == "pilot-evaluate":
        return _pilot_evaluate(args)
    if args.command == "qsts":
        return _qsts(args)
    if args.command == "qsts-benchmark":
        return _qsts_benchmark(args)
    if args.command == "qsts-parallel":
        return _qsts_parallel(args)
    if args.command == "qsts-resize":
        return _qsts_resize(args)
    if args.command == "qsts-sweep":
        return _qsts_sweep(args)
    if args.command == "compare-validation":
        return _compare_validation(args)
    if args.command == "select-stratified-candidates":
        return _select_stratified_candidates(args)
    if args.command == "select-full-year-candidates":
        return _select_full_year_candidates(args)
    if args.command == "render-bundle":
        return _render_bundle(args)
    if args.command == "run-pipeline":
        return _run_pipeline(args)
    if args.command == "validate-client-network":
        return _validate_client_network(args)
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
    portfolio_screen = subparsers.add_parser(
        "portfolio-screen",
        help="Rank a client BESS portfolio using French public grid evidence",
    )
    portfolio_screen.add_argument(
        "--portfolio",
        required=True,
        type=Path,
        help="Client portfolio CSV",
    )
    portfolio_screen.add_argument(
        "--cartostock",
        required=True,
        type=Path,
        help="Cartostock semicolon-delimited CSV",
    )
    portfolio_screen.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Client bundle output directory",
    )
    portfolio_screen.add_argument(
        "--rte7000-revision",
        required=True,
        help="Immutable OpenSynth/rte7000 Git commit SHA",
    )
    portfolio_screen.add_argument("--rte7000-year", type=int, default=2023)
    portfolio_screen.add_argument("--rte7000-month", type=int, default=1)
    portfolio_screen.add_argument(
        "--rte7000-snapshot",
        default="2023-01-01T00:00:00",
        help="ISO-8601 timestamp used for the projected RTE7000 substation snapshot",
    )
    portfolio_screen.add_argument(
        "--search-radius-km",
        type=float,
        default=50.0,
        help="Bounded OSM substation search radius from 1 to 100 km",
    )
    portfolio_screen.add_argument(
        "--osm-fixture",
        type=Path,
        help="Optional JSON object of Overpass responses keyed by client_site_id",
    )
    portfolio_screen.add_argument(
        "--odre-substations",
        type=Path,
        help="Optional local ODRE substation snapshot used to pin identity matching",
    )
    portfolio_screen.add_argument(
        "--manual-reviews",
        type=Path,
        help="Optional reviewed CSV approving or rejecting Class A sites",
    )
    portfolio_screen.add_argument(
        "--odre-constraints",
        type=Path,
        help="Optional local ODRE contraintes-region.csv for public evidence scoring",
    )
    portfolio_screen.add_argument(
        "--odre-storage-assets",
        type=Path,
        help="Optional local ODRE production/storage registry CSV for public evidence scoring",
    )
    portfolio_screen.add_argument(
        "--odre-regional-loads",
        type=Path,
        help="Optional local ODRE regional withdrawals CSV for public evidence scoring",
    )
    portfolio_screen.add_argument(
        "--eco2mix-annual",
        type=Path,
        help="Optional local ECO2MIX annual TSV export, even when named .xls",
    )
    pilot_evaluate = subparsers.add_parser(
        "pilot-evaluate",
        help="Evaluate interview, pilot, and ground-truth evidence against the V2 roadmap",
    )
    pilot_evaluate.add_argument("--interviews", required=True, type=Path)
    pilot_evaluate.add_argument("--pilots", required=True, type=Path)
    pilot_evaluate.add_argument("--ground-truth", required=True, type=Path)
    pilot_evaluate.add_argument("--output", required=True, type=Path)
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
    qsts.add_argument(
        "--bus-ids-csv",
        type=Path,
        help="CSV with a bus_id column to validate; ignored when --bus-ids is provided",
    )
    qsts.add_argument("--asset", default="bess", help="Asset type; V1 supports only 'bess'")
    qsts.add_argument("--start-hour", type=int, default=0, help="First hourly profile index to validate")
    qsts.add_argument("--duration-hours", type=int, help="Number of hourly profile steps to validate")
    qsts.add_argument(
        "--profile-year",
        type=int,
        default=2026,
        help="Calendar year used to map profile hour indices to timestamps",
    )
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
    _add_selected_policy_argument(qsts, "Decision-frontier policy used for QSTS product decisions")
    _add_power_flow_options(qsts)
    benchmark = subparsers.add_parser(
        "qsts-benchmark",
        help="Run a small QSTS scenario and write reproducible performance metrics",
    )
    _add_qsts_common_arguments(benchmark)
    _add_power_flow_options(benchmark)
    parallel = subparsers.add_parser(
        "qsts-parallel",
        help="Run QSTS one bus per worker and merge qsts_results.csv outputs",
    )
    _add_qsts_common_arguments(parallel)
    _add_power_flow_options(parallel)
    parallel.add_argument("--workers", type=int, default=1, help="Parallel bus workers")
    parallel.add_argument(
        "--resume",
        action="store_true",
        help="Skip bus_N workers that already contain qsts_results.csv",
    )
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
    resize.add_argument("--profile-year", type=int, default=2026)
    resize.add_argument("--sample-every-n-hours", type=int, default=1)
    resize.add_argument("--stratified-sample", action="store_true")
    resize.add_argument("--voltage-min-pu", type=float, default=0.95)
    resize.add_argument("--voltage-max-pu", type=float, default=1.05)
    resize.add_argument("--max-loading-percent", type=float, default=100.0)
    resize.add_argument("--p90-curtailment-tolerance-mw", type=float, default=0.0)
    resize.add_argument("--expected-curtailment-tolerance-mwh", type=float, default=0.0)
    resize.add_argument(
        "--selected-policy",
        default="standard",
        choices=["strict", "standard", "flexible", "aggressive"],
        help="Decision-frontier policy used for qsts-resize product decisions",
    )
    resize.add_argument("--progress-every-n-hours", type=int, default=250)
    resize.add_argument("--storage-duration-hours", type=float, default=4.0)
    resize.add_argument("--capex-eur-per-kw", type=float, default=0.0)
    resize.add_argument("--fixed-opex-eur-per-kw-year", type=float, default=0.0)
    resize.add_argument("--gross-revenue-eur-per-mw-year", type=float, default=0.0)
    resize.add_argument("--curtailment-penalty-eur-per-mwh", type=float, default=100.0)
    resize.add_argument("--reinforcement-wait-years", type=float, default=5.0)
    resize.add_argument("--discount-rate", type=float, default=0.08)
    _add_power_flow_options(resize)
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
    compare.add_argument(
        "--decision-frontier",
        type=Path,
        nargs="*",
        default=(),
        help="Optional decision_frontier.csv files used for policy-based final decisions",
    )
    compare.add_argument(
        "--selected-policy",
        default="standard",
        choices=["strict", "standard", "flexible", "aggressive"],
        help="Policy used as final_decision when decision frontier rows are available",
    )
    compare.add_argument("--output", required=True, type=Path, help="Output directory")
    select_stratified = subparsers.add_parser(
        "select-stratified-candidates",
        help="Select a balanced set of buses for stratified QSTS",
    )
    select_stratified.add_argument("--screening-csv", required=True, type=Path)
    select_stratified.add_argument("--output", required=True, type=Path)
    select_stratified.add_argument("--max-candidates", type=int, default=DEFAULT_STRATIFIED_MAX_CANDIDATES)
    select_stratified.add_argument("--top-go-candidates", type=int, default=DEFAULT_STRATIFIED_TOP_GO_CANDIDATES)
    select_stratified.add_argument(
        "--borderline-candidates",
        type=int,
        default=DEFAULT_STRATIFIED_BORDERLINE_CANDIDATES,
    )
    select_stratified.add_argument(
        "--near-threshold-no-go-candidates",
        type=int,
        default=DEFAULT_STRATIFIED_NEAR_THRESHOLD_NO_GO_CANDIDATES,
    )
    select_stratified.add_argument(
        "--constraint-diverse-candidates",
        type=int,
        default=DEFAULT_STRATIFIED_CONSTRAINT_DIVERSE_CANDIDATES,
    )
    select_full_year = subparsers.add_parser(
        "select-full-year-candidates",
        help="Select a balanced set of QSTS full-year candidates",
    )
    select_full_year.add_argument("--screening-csv", required=True, type=Path)
    select_full_year.add_argument("--stratified-csv", type=Path)
    select_full_year.add_argument("--validation-matrix-csv", type=Path)
    select_full_year.add_argument("--output", required=True, type=Path)
    select_full_year.add_argument("--max-candidates", type=int, default=DEFAULT_FULL_YEAR_MAX_CANDIDATES)
    select_full_year.add_argument("--top-candidates", type=int, default=DEFAULT_FULL_YEAR_TOP_CANDIDATES)
    select_full_year.add_argument(
        "--borderline-candidates",
        type=int,
        default=DEFAULT_FULL_YEAR_BORDERLINE_CANDIDATES,
    )
    select_full_year.add_argument(
        "--false-positive-suspects",
        type=int,
        default=DEFAULT_FULL_YEAR_FALSE_POSITIVE_SUSPECTS,
    )
    select_full_year.add_argument("--bad-controls", type=int, default=DEFAULT_FULL_YEAR_BAD_CONTROLS)
    bundle = subparsers.add_parser(
        "render-bundle",
        help="Render HTML report, scorecard, and next-campaign guide for an investor bundle",
    )
    bundle.add_argument("--bundle", required=True, type=Path, help="Investor bundle directory")
    pipeline = subparsers.add_parser(
        "run-pipeline",
        help="Run the BESS pre-feasibility pipeline",
    )
    pipeline.add_argument("--network", required=True, help="SimBench code, or 'toy' for smoke tests")
    pipeline.add_argument("--requested-mw", required=True, type=float, help="Requested BESS MW")
    pipeline.add_argument("--output", required=True, type=Path, help="Output directory")
    pipeline.add_argument("--asset", default="bess", help="Asset type; V1 supports only 'bess'")
    pipeline.add_argument("--top-n", type=int, default=10, help="Rows to show in pipeline report")
    pipeline.add_argument("--max-buses", type=int, help="Maximum candidate buses to screen")
    pipeline.add_argument(
        "--candidate-policy",
        default="mv_active",
        choices=["mv_active"],
        help="Candidate bus selection policy",
    )
    pipeline.add_argument(
        "--data-source-type",
        default="benchmark",
        choices=["benchmark", "client_model", "public_reconstruction", "operator_validated"],
        help="Evidence data-source label used in pipeline outputs",
    )
    pipeline.add_argument("--curtailment-tolerance-mwh", type=float, default=0.0)
    pipeline.add_argument("--p90-curtailment-tolerance-mw", type=float, default=0.0)
    pipeline.add_argument("--reinforcement-wait-years", type=float, default=5.0)
    pipeline.add_argument("--gross-margin-eur-per-mwh", type=float, default=0.0)
    pipeline.add_argument("--curtailment-penalty-eur-per-mwh", type=float, default=100.0)
    pipeline.add_argument("--waiting-cost-eur-per-mw-year", type=float, default=50_000.0)
    pipeline.add_argument("--storage-duration-hours", type=float, default=4.0)
    pipeline.add_argument("--round-trip-efficiency", type=float, default=0.9)
    pipeline.add_argument("--soc-min-fraction", type=float, default=0.0)
    pipeline.add_argument("--soc-max-fraction", type=float, default=1.0)
    pipeline.add_argument(
        "--run-qsts-stratified",
        action="store_true",
        help="Run stratified QSTS for the selected candidate shortlist",
    )
    pipeline.add_argument(
        "--run-qsts-full-year",
        action="store_true",
        help="Run full-year QSTS for selected finalists; requires --run-qsts-stratified",
    )
    pipeline.add_argument(
        "--run-resize-on-no-go",
        action="store_true",
        help="Run QSTS resize scenarios for the first full-year no-go finalist",
    )
    pipeline.add_argument("--qsts-start-hour", type=int, default=0)
    pipeline.add_argument("--qsts-duration-hours", type=int)
    pipeline.add_argument("--qsts-profile-year", type=int, default=2026)
    pipeline.add_argument("--qsts-sample-every-n-hours", type=int, default=1)
    pipeline.add_argument("--qsts-progress-every-n-hours", type=int, default=250)
    pipeline.add_argument("--qsts-voltage-min-pu", type=float, default=0.95)
    pipeline.add_argument("--qsts-voltage-max-pu", type=float, default=1.05)
    pipeline.add_argument("--qsts-max-loading-percent", type=float, default=100.0)
    pipeline.add_argument("--qsts-p90-curtailment-tolerance-mw", type=float, default=0.0)
    pipeline.add_argument("--qsts-expected-curtailment-tolerance-mwh", type=float, default=0.0)
    pipeline.add_argument(
        "--stratified-max-candidates",
        type=int,
        default=DEFAULT_STRATIFIED_MAX_CANDIDATES,
    )
    pipeline.add_argument(
        "--stratified-top-go-candidates",
        type=int,
        default=DEFAULT_STRATIFIED_TOP_GO_CANDIDATES,
    )
    pipeline.add_argument(
        "--stratified-borderline-candidates",
        type=int,
        default=DEFAULT_STRATIFIED_BORDERLINE_CANDIDATES,
    )
    pipeline.add_argument(
        "--stratified-near-threshold-no-go-candidates",
        type=int,
        default=DEFAULT_STRATIFIED_NEAR_THRESHOLD_NO_GO_CANDIDATES,
    )
    pipeline.add_argument(
        "--stratified-constraint-diverse-candidates",
        type=int,
        default=DEFAULT_STRATIFIED_CONSTRAINT_DIVERSE_CANDIDATES,
    )
    pipeline.add_argument("--full-year-max-candidates", type=int, default=DEFAULT_FULL_YEAR_MAX_CANDIDATES)
    pipeline.add_argument("--full-year-top-candidates", type=int, default=DEFAULT_FULL_YEAR_TOP_CANDIDATES)
    pipeline.add_argument(
        "--full-year-borderline-candidates",
        type=int,
        default=DEFAULT_FULL_YEAR_BORDERLINE_CANDIDATES,
    )
    pipeline.add_argument(
        "--full-year-false-positive-suspects",
        type=int,
        default=DEFAULT_FULL_YEAR_FALSE_POSITIVE_SUSPECTS,
    )
    pipeline.add_argument("--full-year-bad-controls", type=int, default=DEFAULT_FULL_YEAR_BAD_CONTROLS)
    pipeline.add_argument("--resize-min-mw", type=float, default=1.0)
    pipeline.add_argument("--resize-step-mw", type=float, default=1.0)
    pipeline.add_argument(
        "--resize-selected-policy",
        default="standard",
        choices=["strict", "standard", "flexible", "aggressive"],
    )
    pipeline.add_argument("--resize-max-buses", type=int, default=1)
    validate_client = subparsers.add_parser(
        "validate-client-network",
        help="Validate a client_network input package",
    )
    validate_client.add_argument(
        "--client-network",
        required=True,
        type=Path,
        help="Path to client_network directory",
    )
    validate_client.add_argument("--output", required=True, type=Path, help="Output directory")
    return parser


def _add_qsts_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--network", required=True, help="SimBench code; 'toy' is refused for QSTS")
    parser.add_argument("--screening-csv", required=True, type=Path, help="Input screening.csv path")
    parser.add_argument("--requested-mw", required=True, type=float, help="Requested BESS MW")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    parser.add_argument("--top-n", type=int, default=10, help="Top screening rows to validate")
    parser.add_argument(
        "--bus-ids",
        help="Comma-separated screening bus IDs to validate; overrides --top-n selection",
    )
    parser.add_argument(
        "--bus-ids-csv",
        type=Path,
        help="CSV with a bus_id column to validate; ignored when --bus-ids is provided",
    )
    parser.add_argument("--asset", default="bess", help="Asset type; V1 supports only 'bess'")
    parser.add_argument("--start-hour", type=int, default=0, help="First hourly profile index to validate")
    parser.add_argument("--duration-hours", type=int, help="Number of hourly profile steps to validate")
    parser.add_argument(
        "--profile-year",
        type=int,
        default=2026,
        help="Calendar year used to map profile hour indices to timestamps",
    )
    parser.add_argument("--sample-every-n-hours", type=int, default=1)
    parser.add_argument("--stratified-sample", action="store_true")
    parser.add_argument("--voltage-min-pu", type=float, default=0.95)
    parser.add_argument("--voltage-max-pu", type=float, default=1.05)
    parser.add_argument("--max-loading-percent", type=float, default=100.0)
    parser.add_argument("--p90-curtailment-tolerance-mw", type=float, default=0.0)
    parser.add_argument("--expected-curtailment-tolerance-mwh", type=float, default=0.0)
    parser.add_argument("--progress-every-n-hours", type=int, default=250)
    parser.add_argument("--storage-duration-hours", type=float, default=4.0)
    parser.add_argument("--capex-eur-per-kw", type=float, default=0.0)
    parser.add_argument("--fixed-opex-eur-per-kw-year", type=float, default=0.0)
    parser.add_argument("--gross-revenue-eur-per-mw-year", type=float, default=0.0)
    parser.add_argument("--curtailment-penalty-eur-per-mwh", type=float, default=100.0)
    parser.add_argument("--reinforcement-wait-years", type=float, default=5.0)
    parser.add_argument("--discount-rate", type=float, default=0.08)
    _add_selected_policy_argument(parser, "Decision-frontier policy used for QSTS product decisions")


def _add_selected_policy_argument(parser: argparse.ArgumentParser, help_text: str) -> None:
    parser.add_argument(
        "--selected-policy",
        default="standard",
        choices=["strict", "standard", "flexible", "aggressive"],
        help=help_text,
    )


def _add_power_flow_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pf-numba", action="store_true", help="Enable pandapower runpp numba")
    parser.add_argument(
        "--pf-algorithm",
        default="nr",
        choices=["nr", "iwamoto_nr", "bfsw", "gs", "fdbx", "fdxb"],
        help="pandapower runpp algorithm",
    )
    parser.add_argument(
        "--pf-init",
        default="auto",
        choices=["auto", "flat", "dc", "results"],
        help="pandapower runpp initialization mode",
    )
    parser.add_argument(
        "--pf-recycle",
        action="store_true",
        help="Enable conservative pandapower runpp recycling for repeated QSTS power flows",
    )


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


def _portfolio_screen(args: argparse.Namespace) -> int:
    try:
        result = run_portfolio_workflow(
            PortfolioWorkflowRequest(
                portfolio_path=args.portfolio,
                cartostock_path=args.cartostock,
                output_dir=args.output,
                rte7000_revision=args.rte7000_revision,
                rte7000_year=args.rte7000_year,
                rte7000_month=args.rte7000_month,
                rte7000_snapshot=args.rte7000_snapshot,
                search_radius_km=args.search_radius_km,
                osm_fixture_path=args.osm_fixture,
                odre_substations_path=args.odre_substations,
                manual_reviews_path=args.manual_reviews,
                odre_constraints_path=args.odre_constraints,
                odre_storage_assets_path=args.odre_storage_assets,
                odre_regional_loads_path=args.odre_regional_loads,
                eco2mix_annual_path=args.eco2mix_annual,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"portfolio-screen error: {exc}")
        return 2
    print(
        f"portfolio-screen ranked {len(result.screening.ranked_sites)} sites: "
        f"{result.outputs.report_path} {result.outputs.manifest_path}"
    )
    return 0


def _pilot_evaluate(args: argparse.Namespace) -> int:
    try:
        outputs = run_commercial_validation(
            interviews_path=args.interviews,
            pilots_path=args.pilots,
            ground_truth_path=args.ground_truth,
            output_dir=args.output,
        )
    except (CommercialValidationError, OSError, ValueError) as exc:
        print(f"pilot-evaluate error: {exc}")
        return 2
    print(
        f"pilot-evaluate: {outputs.summary_path} {outputs.report_path}"
    )
    return 0


def _qsts(args: argparse.Namespace) -> int:
    try:
        request = _qsts_request_from_args(args)
        settings = _constraint_settings_from_args(args)
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


def _qsts_benchmark(args: argparse.Namespace) -> int:
    try:
        request = _qsts_request_from_args(args)
        settings = _constraint_settings_from_args(args)
        result = run_qsts(request, settings=settings)
    except (ImportError, ValueError) as exc:
        print(f"qsts-benchmark error: {exc}")
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    write_qsts_outputs(result, args.output / "qsts_output", command=args._argv)
    csv_path = args.output / "qsts_benchmark.csv"
    row = _qsts_benchmark_row(result)
    _write_rows(csv_path, [row], row.keys())
    markdown_path = args.output / "qsts_benchmark.md"
    markdown_path.write_text(_render_qsts_benchmark_markdown(row), encoding="utf-8")
    print(f"qsts benchmark: {csv_path} {markdown_path}")
    return 0


def _qsts_parallel(args: argparse.Namespace) -> int:
    try:
        request = _qsts_request_from_args(args)
        settings = _constraint_settings_from_args(args)
        if not request.bus_ids:
            raise ValueError("qsts-parallel requires --bus-ids for explicit worker outputs")
        if args.workers <= 0:
            raise ValueError("--workers must be positive")
    except ValueError as exc:
        print(f"qsts-parallel error: {exc}")
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    worker_specs = [
        (bus_id, args.output / f"bus_{bus_id}")
        for bus_id in request.bus_ids
        if not (args.resume and (args.output / f"bus_{bus_id}" / "qsts_results.csv").exists())
    ]
    completed_dirs = [args.output / f"bus_{bus_id}" for bus_id in request.bus_ids]
    try:
        if args.workers == 1:
            for bus_id, output_dir in worker_specs:
                _run_qsts_worker(request, settings, bus_id, output_dir, args._argv)
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                futures = [
                    executor.submit(_run_qsts_worker, request, settings, bus_id, output_dir, args._argv)
                    for bus_id, output_dir in worker_specs
                ]
                for future in as_completed(futures):
                    future.result()
    except (ImportError, ValueError) as exc:
        print(f"qsts-parallel error: {exc}")
        return 2

    merged_dir = args.output / "merged"
    _merge_qsts_worker_outputs(completed_dirs, merged_dir)
    print(f"qsts-parallel completed {len(worker_specs)} workers: {merged_dir / 'qsts_results.csv'}")
    return 0


def _qsts_request_from_args(
    args: argparse.Namespace,
    *,
    bus_ids: tuple[int, ...] | None = None,
    requested_mw: float | None = None,
) -> QstsRequest:
    return QstsRequest(
        network_code=args.network,
        screening_csv=args.screening_csv,
        requested_mw=args.requested_mw if requested_mw is None else requested_mw,
        top_n=args.top_n,
        bus_ids=_qsts_bus_ids_from_args(args) if bus_ids is None else bus_ids,
        asset=args.asset,
        start_hour=args.start_hour,
        duration_hours=args.duration_hours,
        profile_year=args.profile_year,
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
        pf_numba=args.pf_numba,
        pf_algorithm=args.pf_algorithm,
        pf_init=args.pf_init,
        pf_recycle=args.pf_recycle,
        selected_policy=args.selected_policy,
    )


def _constraint_settings_from_args(args: argparse.Namespace) -> ConstraintSettings:
    return ConstraintSettings(
        min_vm_pu=args.voltage_min_pu,
        max_vm_pu=args.voltage_max_pu,
        max_loading_percent=args.max_loading_percent,
    )


def _run_qsts_worker(
    base_request: QstsRequest,
    settings: ConstraintSettings,
    bus_id: int,
    output_dir: Path,
    command: Sequence[str],
) -> str:
    request = QstsRequest(
        **{
            **base_request.__dict__,
            "bus_ids": (bus_id,),
            "top_n": 1,
            "progress_every_n_hours": 0,
        }
    )
    result = run_qsts(request, settings=settings)
    write_qsts_outputs(result, output_dir, command=tuple(command) + ("--worker-bus-id", str(bus_id)))
    return output_dir.as_posix()


def _merge_qsts_worker_outputs(worker_dirs: Sequence[Path], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        "qsts_results.csv",
        "decision_frontier.csv",
        "qsts_economics.csv",
        "qsts_risk_summary.csv",
    ):
        _merge_csv_files([worker_dir / filename for worker_dir in worker_dirs], output_dir / filename)
    _merge_qsts_performance(worker_dirs, output_dir / "qsts_performance.json")
    manifest_path = output_dir / "parallel_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "qsts-parallel-merge-v1",
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "worker_dirs": [worker_dir.as_posix() for worker_dir in worker_dirs],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _merge_csv_files(input_paths: Sequence[Path], output_path: Path) -> None:
    fieldnames: list[str] | None = None
    rows: list[dict[str, str]] = []
    for path in input_paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                continue
            if fieldnames is None:
                fieldnames = list(reader.fieldnames)
            rows.extend({key: row.get(key, "") for key in fieldnames} for row in reader)
    if fieldnames is None:
        output_path.write_text("", encoding="utf-8")
        return
    _write_rows(output_path, rows, fieldnames)


def _merge_qsts_performance(worker_dirs: Sequence[Path], output_path: Path) -> None:
    worker_stats = []
    for worker_dir in worker_dirs:
        path = worker_dir / "qsts_performance.json"
        if path.exists():
            worker_stats.append(json.loads(path.read_text(encoding="utf-8")))
    if not worker_stats:
        output_path.write_text("{}\n", encoding="utf-8")
        return

    summed_fields = (
        "runtime_seconds",
        "power_flow_calls",
        "baseline_power_flow_calls",
        "candidate_power_flow_calls",
        "binary_search_count",
        "baseline_cache_hits",
        "baseline_cache_misses",
        "evaluated_buses",
        "evaluated_bus_hours",
    )
    merged: dict[str, object] = {
        field: sum(float(stats.get(field, 0.0)) for stats in worker_stats)
        for field in summed_fields
    }
    integer_fields = (
        "power_flow_calls",
        "baseline_power_flow_calls",
        "candidate_power_flow_calls",
        "binary_search_count",
        "baseline_cache_hits",
        "baseline_cache_misses",
        "evaluated_buses",
        "evaluated_bus_hours",
    )
    for field in integer_fields:
        merged[field] = int(merged[field])
    merged["evaluated_time_steps"] = max(
        int(stats.get("evaluated_time_steps", 0)) for stats in worker_stats
    )
    bus_hours = int(merged["evaluated_bus_hours"])
    runtime_seconds = float(merged["runtime_seconds"])
    power_flow_calls = int(merged["power_flow_calls"])
    merged["power_flow_calls_per_bus_hour"] = (
        power_flow_calls / bus_hours if bus_hours else 0.0
    )
    merged["runtime_seconds_per_bus_hour"] = runtime_seconds / bus_hours if bus_hours else 0.0
    merged["parallelization_unit"] = "bus"
    merged["worker_count"] = len(worker_stats)
    merged["total_full_year_runtime_seconds"] = runtime_seconds
    output_path.write_text(
        json.dumps(merged, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_rows(path: Path, rows: Sequence[dict[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _qsts_benchmark_row(result) -> dict[str, object]:
    request = result.request
    performance = result.performance
    return {
        "network_code": request.network_code,
        "requested_mw": f"{request.requested_mw:.6f}",
        "bus_ids": ",".join(str(bus_id) for bus_id in request.bus_ids),
        "duration_hours": "" if request.duration_hours is None else str(request.duration_hours),
        "stratified_sample": str(request.stratified_sample),
        "pf_numba": str(request.pf_numba),
        "pf_algorithm": request.pf_algorithm,
        "pf_init": request.pf_init,
        "pf_recycle": str(request.pf_recycle),
        "evaluated_time_steps": performance.evaluated_time_steps,
        "evaluated_buses": performance.evaluated_buses,
        "evaluated_bus_hours": performance.evaluated_bus_hours,
        "power_flow_calls": performance.power_flow_calls,
        "power_flow_calls_per_bus_hour": f"{performance.power_flow_calls_per_bus_hour:.6f}",
        "runtime_seconds": f"{performance.runtime_seconds:.6f}",
        "runtime_seconds_per_bus_hour": f"{performance.runtime_seconds_per_bus_hour:.6f}",
    }


def _render_qsts_benchmark_markdown(row: dict[str, object]) -> str:
    lines = [
        "# QSTS Benchmark",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key, value in row.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines) + "\n"


def _qsts_resize(args: argparse.Namespace) -> int:
    try:
        settings = ConstraintSettings(
            min_vm_pu=args.voltage_min_pu,
            max_vm_pu=args.voltage_max_pu,
            max_loading_percent=args.max_loading_percent,
        )
        result = run_resize_scenarios(
            ResizeRequest(
                network_code=args.network,
                screening_csv=args.screening_csv,
                bus_id=args.bus_id,
                original_requested_mw=args.requested_mw,
                min_mw=args.min_mw,
                step_mw=args.step_mw,
                output_dir=args.output / "scenarios",
                asset=args.asset,
                start_hour=args.start_hour,
                duration_hours=args.duration_hours,
                profile_year=args.profile_year,
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
                selected_policy=args.selected_policy,
                pf_numba=args.pf_numba,
                pf_algorithm=args.pf_algorithm,
                pf_init=args.pf_init,
                pf_recycle=args.pf_recycle,
            ),
            settings=settings,
            qsts_runner=run_qsts,
        )
        outputs = write_resize_outputs(result, args.output)
    except (ImportError, ValueError) as exc:
        print(f"qsts-resize error: {exc}")
        return 2

    print(
        f"qsts-resize completed {len(result.rows)} scenarios: "
        f"{outputs.csv_path} {outputs.summary_path}"
    )
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
            profile_year=int(config.get("profile_year", 2026)),
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
        decision_frontier_csvs=tuple(args.decision_frontier),
        selected_policy=args.selected_policy,
    )
    outputs = write_validation_matrix_outputs(matrix, args.output)
    print(f"validation matrix: {outputs.csv_path} {outputs.markdown_path}")
    return 0


def _select_stratified_candidates(args: argparse.Namespace) -> int:
    candidates = select_stratified_candidates(
        StratifiedSelectionRequest(
            screening_csv=args.screening_csv,
            max_candidates=args.max_candidates,
            top_go_candidates=args.top_go_candidates,
            borderline_candidates=args.borderline_candidates,
            near_threshold_no_go_candidates=args.near_threshold_no_go_candidates,
            constraint_diverse_candidates=args.constraint_diverse_candidates,
        )
    )
    output = write_stratified_selection_csv(candidates, args.output)
    print(f"stratified candidate selection: {output}")
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


def _run_pipeline(args: argparse.Namespace) -> int:
    try:
        result = run_pipeline(
            PipelineRequest(
                network_code=args.network,
                requested_mw=args.requested_mw,
                output_dir=args.output,
                asset=args.asset,
                top_n=args.top_n,
                max_buses=args.max_buses,
                candidate_policy=args.candidate_policy,
                data_source_type=args.data_source_type,
                curtailment_tolerance_mwh_per_year=args.curtailment_tolerance_mwh,
                p90_curtailment_tolerance_mw=args.p90_curtailment_tolerance_mw,
                reinforcement_wait_years=args.reinforcement_wait_years,
                economics=EconomicAssumptions(
                    gross_margin_eur_per_mwh=args.gross_margin_eur_per_mwh,
                    curtailment_penalty_eur_per_mwh=args.curtailment_penalty_eur_per_mwh,
                    waiting_cost_eur_per_mw_year=args.waiting_cost_eur_per_mw_year,
                ),
                storage_duration_hours=args.storage_duration_hours,
                round_trip_efficiency=args.round_trip_efficiency,
                soc_min_fraction=args.soc_min_fraction,
                soc_max_fraction=args.soc_max_fraction,
                run_qsts_stratified=args.run_qsts_stratified,
                run_qsts_full_year=args.run_qsts_full_year,
                qsts_start_hour=args.qsts_start_hour,
                qsts_duration_hours=args.qsts_duration_hours,
                qsts_profile_year=args.qsts_profile_year,
                qsts_sample_every_n_hours=args.qsts_sample_every_n_hours,
                qsts_progress_every_n_hours=args.qsts_progress_every_n_hours,
                qsts_voltage_min_pu=args.qsts_voltage_min_pu,
                qsts_voltage_max_pu=args.qsts_voltage_max_pu,
                qsts_max_loading_percent=args.qsts_max_loading_percent,
                qsts_p90_curtailment_tolerance_mw=args.qsts_p90_curtailment_tolerance_mw,
                qsts_expected_curtailment_tolerance_mwh=(
                    args.qsts_expected_curtailment_tolerance_mwh
                ),
                stratified_max_candidates=args.stratified_max_candidates,
                stratified_top_go_candidates=args.stratified_top_go_candidates,
                stratified_borderline_candidates=args.stratified_borderline_candidates,
                stratified_near_threshold_no_go_candidates=(
                    args.stratified_near_threshold_no_go_candidates
                ),
                stratified_constraint_diverse_candidates=(
                    args.stratified_constraint_diverse_candidates
                ),
                full_year_max_candidates=args.full_year_max_candidates,
                full_year_top_candidates=args.full_year_top_candidates,
                full_year_borderline_candidates=args.full_year_borderline_candidates,
                full_year_false_positive_suspects=args.full_year_false_positive_suspects,
                full_year_bad_controls=args.full_year_bad_controls,
                run_resize_on_no_go=args.run_resize_on_no_go,
                resize_min_mw=args.resize_min_mw,
                resize_step_mw=args.resize_step_mw,
                resize_selected_policy=args.resize_selected_policy,
                resize_max_buses=args.resize_max_buses,
            )
        )
    except (ImportError, ValueError) as exc:
        print(f"run-pipeline error: {exc}")
        return 2
    print(f"pipeline: {result.report_path} {result.manifest_path}")
    return 0


def _validate_client_network(args: argparse.Namespace) -> int:
    result = validate_client_network(args.client_network)
    outputs = write_client_network_validation(result, args.output)
    print(f"client-network validation: {outputs.json_path} {outputs.markdown_path}")
    return 0 if result.valid else 2


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


def _qsts_bus_ids_from_args(args: argparse.Namespace) -> tuple[int, ...]:
    explicit = _parse_bus_ids(args.bus_ids)
    if explicit:
        return explicit
    csv_path = getattr(args, "bus_ids_csv", None)
    if csv_path is None:
        return ()
    return _parse_bus_ids_csv(csv_path)


def _parse_bus_ids_csv(path: Path) -> tuple[int, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if rows and "bus_id" not in rows[0]:
        raise ValueError("bus IDs CSV must include a bus_id column")
    bus_ids: list[int] = []
    seen: set[int] = set()
    for row in rows:
        value = row.get("bus_id", "").strip()
        if not value:
            continue
        bus_id = int(value)
        if bus_id in seen:
            continue
        seen.add(bus_id)
        bus_ids.append(bus_id)
    return tuple(bus_ids)


def _config_bus_ids(config: dict[str, object]) -> tuple[int, ...]:
    if "bus_ids" not in config:
        return ()
    return tuple(int(bus_id) for bus_id in config["bus_ids"])


if __name__ == "__main__":
    raise SystemExit(main())
