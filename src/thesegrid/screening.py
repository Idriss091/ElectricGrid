from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from thesegrid.assessment import ASSUMPTIONS, SCIENTIFIC_UNCERTAINTY, assess_connection
from thesegrid.models import ConnectionRequest, EconomicAssumptions, Verdict
from thesegrid.networks import load_network

CandidatePolicy = Literal["mv_active"]

RANKING_POLICY = (
    "verdict > flexible_value_delta_eur > conditional_capacity_mw > "
    "p90_curtailment_mw > firm_capacity_mw"
)

CSV_COLUMNS = (
    "rank",
    "bus_id",
    "bus_name",
    "vn_kv",
    "verdict",
    "firm_injection_mw",
    "firm_withdrawal_mw",
    "firm_capacity_mw",
    "conditional_capacity_mw",
    "evaluated_conditional_mw",
    "recommended_envelope",
    "expected_curtailment_hours",
    "expected_curtailment_mwh",
    "p50_curtailment_mw",
    "p90_curtailment_mw",
    "ebitda_at_risk_eur",
    "flexible_value_delta_eur",
    "main_constraint",
)


@dataclass(frozen=True)
class ScreeningRequest:
    network_code: str
    requested_mw: float
    asset: str = "bess"
    top_n: int = 10
    candidate_policy: CandidatePolicy = "mv_active"
    curtailment_tolerance_mwh_per_year: float = 0.0
    p90_curtailment_tolerance_mw: float = 0.0
    reinforcement_wait_years: float = 5.0
    economics: EconomicAssumptions = field(default_factory=EconomicAssumptions)

    def __post_init__(self) -> None:
        if not self.network_code:
            raise ValueError("network_code must not be empty")
        if self.requested_mw <= 0:
            raise ValueError("requested_mw must be positive")
        if self.asset.lower() != "bess":
            raise ValueError("V1 supports BESS assets only")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")
        if self.candidate_policy != "mv_active":
            raise ValueError("candidate_policy must be 'mv_active'")


@dataclass(frozen=True)
class ScreeningRow:
    rank: int
    bus_id: int
    bus_name: str
    vn_kv: float | None
    verdict: Verdict | str
    firm_injection_mw: float
    firm_withdrawal_mw: float
    firm_capacity_mw: float
    conditional_capacity_mw: float
    evaluated_conditional_mw: float
    recommended_envelope: str
    expected_curtailment_hours: int
    expected_curtailment_mwh: float
    p50_curtailment_mw: float
    p90_curtailment_mw: float
    ebitda_at_risk_eur: float
    flexible_value_delta_eur: float
    main_constraint: str


@dataclass(frozen=True)
class ScreeningResult:
    request: ScreeningRequest
    rows: tuple[ScreeningRow, ...]
    top_rows: tuple[ScreeningRow, ...]
    network_code: str
    requested_mw: float
    ranking_policy: str


@dataclass(frozen=True)
class ScreeningOutputPaths:
    csv_path: Path
    summary_path: Path


def screen_connections(request: ScreeningRequest, net: object | None = None) -> ScreeningResult:
    network = load_network(request.network_code) if net is None else net
    rows = [
        _screen_bus(request, network, bus_id)
        for bus_id in candidate_bus_ids(network, request.candidate_policy)
    ]
    ranked = sort_screening_rows(tuple(rows))
    return ScreeningResult(
        request=request,
        rows=ranked,
        top_rows=ranked[: request.top_n],
        network_code=request.network_code,
        requested_mw=request.requested_mw,
        ranking_policy=RANKING_POLICY,
    )


def candidate_bus_ids(net: object, policy: CandidatePolicy) -> tuple[int, ...]:
    if policy != "mv_active":
        raise ValueError("candidate_policy must be 'mv_active'")

    bus = net.bus
    excluded = _excluded_bus_ids(net)
    active = _active_bus_ids(net)
    if "vn_kv" in bus:
        mv = {
            int(bus_id)
            for bus_id, row in bus.iterrows()
            if _is_mv_voltage(row["vn_kv"]) and int(bus_id) in active and int(bus_id) not in excluded
        }
        if mv:
            return tuple(sorted(mv))

    fallback = tuple(sorted(bus_id for bus_id in active if bus_id not in excluded))
    return fallback


def sort_screening_rows(rows: tuple[ScreeningRow, ...]) -> tuple[ScreeningRow, ...]:
    sorted_rows = sorted(rows, key=_ranking_key)
    return tuple(
        ScreeningRow(
            **{
                **asdict(row),
                "rank": rank,
            }
        )
        for rank, row in enumerate(sorted_rows, start=1)
    )


def write_screening_outputs(result: ScreeningResult, output_dir: Path) -> ScreeningOutputPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "screening.csv"
    summary_path = output_dir / "screening_summary.md"
    write_screening_csv(result, csv_path)
    summary_path.write_text(render_screening_summary(result), encoding="utf-8")
    return ScreeningOutputPaths(csv_path=csv_path, summary_path=summary_path)


def write_screening_csv(result: ScreeningResult, csv_path: Path) -> Path:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in result.rows:
            writer.writerow({column: asdict(row)[column] for column in CSV_COLUMNS})
    return csv_path


def render_screening_summary(result: ScreeningResult) -> str:
    if not result.rows:
        top_section = "No candidate bus passed the screening candidate policy."
        best_bus = "None"
    else:
        best = result.rows[0]
        best_bus = f"{best.bus_id} ({best.bus_name})"
        top_section = _render_top_table(result.top_rows)

    verdict_counts = _verdict_counts(result.rows)
    constraints = _constraint_counts(result.rows)
    assumptions = "\n".join(f"- {assumption}" for assumption in ASSUMPTIONS)
    uncertainty = "\n".join(f"- {item}" for item in SCIENTIFIC_UNCERTAINTY)
    return f"""# Multi-Bus BESS Screening Summary

This screening is an early-stage buyer-side decision aid. It does not replace an official grid-connection study.

## Request

- network_code: {result.network_code}
- requested_mw: {result.requested_mw:.3f}
- asset: {result.request.asset}
- candidate_policy: {result.request.candidate_policy}
- ranking_policy: {result.ranking_policy}
- evaluated_buses: {len(result.rows)}

## Decision

- best bus: {best_bus}

## Verdict Distribution

- go: {verdict_counts["go"]}
- go-with-conditions: {verdict_counts["go-with-conditions"]}
- no-go: {verdict_counts["no-go"]}

## Top 10

{top_section}

## Frequent Binding Constraints

{constraints}

## Assumptions

{assumptions}

## Remaining Scientific Uncertainty

{uncertainty}
"""


def _screen_bus(request: ScreeningRequest, net: object, bus_id: int) -> ScreeningRow:
    memo = assess_connection(
        ConnectionRequest(
            network_code=request.network_code,
            bus_id=bus_id,
            requested_mw=request.requested_mw,
            asset=request.asset,
            curtailment_tolerance_mwh_per_year=request.curtailment_tolerance_mwh_per_year,
            p90_curtailment_tolerance_mw=request.p90_curtailment_tolerance_mw,
            reinforcement_wait_years=request.reinforcement_wait_years,
            economics=request.economics,
        ),
        net=net,
    )
    return ScreeningRow(
        rank=0,
        bus_id=bus_id,
        bus_name=_bus_name(net, bus_id),
        vn_kv=_bus_voltage(net, bus_id),
        verdict=memo.verdict,
        firm_injection_mw=memo.firm_injection_mw,
        firm_withdrawal_mw=memo.firm_withdrawal_mw,
        firm_capacity_mw=memo.firm_capacity_mw,
        conditional_capacity_mw=memo.conditional_capacity_mw,
        evaluated_conditional_mw=memo.evaluated_conditional_mw,
        recommended_envelope=memo.recommended_envelope,
        expected_curtailment_hours=memo.curtailment.expected_hours,
        expected_curtailment_mwh=memo.curtailment.expected_mwh,
        p50_curtailment_mw=memo.curtailment.p50_mw,
        p90_curtailment_mw=memo.curtailment.p90_mw,
        ebitda_at_risk_eur=memo.economics.ebitda_at_risk_eur,
        flexible_value_delta_eur=memo.economics.flexible_value_delta_eur,
        main_constraint=memo.binding_constraints[0].description if memo.binding_constraints else "",
    )


def _ranking_key(row: ScreeningRow) -> tuple[int, float, float, float, float, int]:
    verdict_rank = {"go": 0, "go-with-conditions": 1, "no-go": 2}
    return (
        verdict_rank[str(row.verdict)],
        -row.flexible_value_delta_eur,
        -row.conditional_capacity_mw,
        row.p90_curtailment_mw,
        -row.firm_capacity_mw,
        row.bus_id,
    )


def _excluded_bus_ids(net: object) -> set[int]:
    excluded = {int(net.bus.index.min())}
    ext_grid = getattr(net, "ext_grid", None)
    if ext_grid is not None and "bus" in ext_grid:
        excluded.update(int(bus_id) for bus_id in ext_grid["bus"].tolist())
    return excluded


def _active_bus_ids(net: object) -> set[int]:
    bus = net.bus
    if "in_service" not in bus:
        return {int(bus_id) for bus_id in bus.index}
    return {
        int(bus_id)
        for bus_id, in_service in bus["in_service"].items()
        if bool(in_service)
    }


def _is_mv_voltage(value: object) -> bool:
    try:
        vn_kv = float(value)
    except (TypeError, ValueError):
        return False
    return 1.0 <= vn_kv < 110.0


def _bus_name(net: object, bus_id: int) -> str:
    if "name" not in net.bus or bus_id not in net.bus.index:
        return ""
    value = net.bus.at[bus_id, "name"]
    return "" if value is None else str(value)


def _bus_voltage(net: object, bus_id: int) -> float | None:
    if "vn_kv" not in net.bus or bus_id not in net.bus.index:
        return None
    value = net.bus.at[bus_id, "vn_kv"]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _render_top_table(rows: tuple[ScreeningRow, ...]) -> str:
    if not rows:
        return "No rows to display."
    lines = [
        "| rank | bus_id | bus_name | verdict | firm_mw | conditional_mw | p90_mw | value_delta_eur |",
        "| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row.rank} | {row.bus_id} | {row.bus_name} | {row.verdict} | "
            f"{row.firm_capacity_mw:.3f} | {row.conditional_capacity_mw:.3f} | "
            f"{row.p90_curtailment_mw:.3f} | {row.flexible_value_delta_eur:.2f} |"
        )
    return "\n".join(lines)


def _verdict_counts(rows: tuple[ScreeningRow, ...]) -> dict[str, int]:
    return {
        "go": sum(1 for row in rows if row.verdict == "go"),
        "go-with-conditions": sum(1 for row in rows if row.verdict == "go-with-conditions"),
        "no-go": sum(1 for row in rows if row.verdict == "no-go"),
    }


def _constraint_counts(rows: tuple[ScreeningRow, ...]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        if not row.main_constraint:
            continue
        counts[row.main_constraint] = counts.get(row.main_constraint, 0) + 1
    if not counts:
        return "- None across evaluated candidate buses."
    return "\n".join(
        f"- {constraint}: {count}"
        for constraint, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    )
