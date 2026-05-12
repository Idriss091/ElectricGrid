from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

from thesegrid.assessment import assess_connection
from thesegrid.constraints import ConstraintSettings
from thesegrid.memo import write_investment_memo
from thesegrid.models import ConnectionRequest, EconomicAssumptions
from thesegrid.qsts import QstsRequest, run_qsts, write_qsts_outputs
from thesegrid.screening import ScreeningRequest, screen_connections, write_screening_outputs


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "assess":
        return _assess(args)
    if args.command == "screen":
        return _screen(args)
    if args.command == "qsts":
        return _qsts(args)
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
            asset=args.asset,
            start_hour=args.start_hour,
            duration_hours=args.duration_hours,
            sample_every_n_hours=args.sample_every_n_hours,
            stratified_sample=args.stratified_sample,
            p90_curtailment_tolerance_mw=args.p90_curtailment_tolerance_mw,
            expected_curtailment_tolerance_mwh=args.expected_curtailment_tolerance_mwh,
        )
        settings = ConstraintSettings(
            min_vm_pu=args.voltage_min_pu,
            max_vm_pu=args.voltage_max_pu,
            max_loading_percent=args.max_loading_percent,
        )
        print(f"validating top {request.top_n} buses with QSTS...", file=sys.stderr)
        result = run_qsts(request, settings=settings)
    except (ImportError, ValueError) as exc:
        print(f"qsts error: {exc}")
        return 2
    outputs = write_qsts_outputs(result, args.output)
    print(f"qsts validated {len(result.buses)} buses: {outputs.results_csv_path} {outputs.summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
