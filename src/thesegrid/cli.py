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
from thesegrid.constraints import ConstraintSettings
from thesegrid.memo import write_investment_memo
from thesegrid.models import ConnectionRequest, EconomicAssumptions
from thesegrid.qsts import QstsRequest, run_qsts, write_qsts_outputs
from thesegrid.screening import ScreeningRequest, screen_connections, write_screening_outputs


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
    if args.command == "qsts-sweep":
        return _qsts_sweep(args)
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
    sweep = subparsers.add_parser("qsts-sweep", help="Run a QSTS sensitivity sweep from JSON")
    sweep.add_argument("--config", required=True, type=Path, help="Sweep JSON config path")
    sweep.add_argument("--output", required=True, type=Path, help="Output directory")
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
        print(f"validating top {request.top_n} buses with QSTS...", file=sys.stderr)
        result = run_qsts(request, settings=settings)
    except (ImportError, ValueError) as exc:
        print(f"qsts error: {exc}")
        return 2
    outputs = write_qsts_outputs(result, args.output, command=args._argv)
    print(f"qsts validated {len(result.buses)} buses: {outputs.results_csv_path} {outputs.summary_path}")
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
    for index, scenario in enumerate(scenarios, start=1):
        scenario_id = f"scenario_{index:03d}"
        scenario_dir = args.output / scenario_id
        request = QstsRequest(
            network_code=config["network_code"],
            screening_csv=Path(config["screening_csv"]),
            requested_mw=scenario["requested_mw"],
            top_n=int(config.get("top_n", 3)),
            stratified_sample=config.get("sampling", "stratified") == "stratified",
            p90_curtailment_tolerance_mw=scenario["p90_curtailment_tolerance_mw"],
            expected_curtailment_tolerance_mwh=scenario[
                "expected_curtailment_tolerance_mwh"
            ],
            progress_every_n_hours=int(config.get("progress_every_n_hours", 0)),
        )
        settings = ConstraintSettings(max_vm_pu=scenario["voltage_max_pu"])
        result = run_qsts(request, settings=settings)
        write_qsts_outputs(
            result,
            scenario_dir,
            command=("qsts-sweep", "--config", str(args.config), "--scenario", scenario_id),
        )
        rows.extend(_sweep_result_rows(scenario_id, scenario, result))

    results_csv = args.output / "sensitivity_results.csv"
    _write_sensitivity_results(results_csv, rows)
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
    return config


def _sweep_scenarios(config: dict[str, object]) -> list[dict[str, float]]:
    keys = (
        "requested_mw",
        "p90_curtailment_tolerance_mw",
        "expected_curtailment_tolerance_mwh",
        "voltage_max_pu",
    )
    scenarios: list[dict[str, float]] = []
    for values in itertools.product(*(config[key] for key in keys)):
        scenarios.append({key: float(value) for key, value in zip(keys, values)})
    return scenarios


def _sweep_result_rows(
    scenario_id: str,
    scenario: dict[str, float],
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
                "requested_mw": f"{scenario['requested_mw']:.6f}",
                "p90_curtailment_tolerance_mw": f"{scenario['p90_curtailment_tolerance_mw']:.6f}",
                "expected_curtailment_tolerance_mwh": (
                    f"{scenario['expected_curtailment_tolerance_mwh']:.6f}"
                ),
                "voltage_max_pu": f"{scenario['voltage_max_pu']:.6f}",
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
            "| scenario | bus_id | verdict | requested_mw | p90_tol_mw | mwh_tol | voltage_max_pu | qsts_p90_mw | qsts_mwh |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in rows:
            lines.append(
                "| "
                f"{row['scenario_id']} | {row['bus_id']} | {row['qsts_verdict']} | "
                f"{row['requested_mw']} | {row['p90_curtailment_tolerance_mw']} | "
                f"{row['expected_curtailment_tolerance_mwh']} | {row['voltage_max_pu']} | "
                f"{row['qsts_p90_curtailment_mw']} | {row['qsts_expected_curtailment_mwh']} |"
            )
        table = "\n".join(lines)
    return f"""# QSTS Sensitivity Summary

{table}
"""


if __name__ == "__main__":
    raise SystemExit(main())
