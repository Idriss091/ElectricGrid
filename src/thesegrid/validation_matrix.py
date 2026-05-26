from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path


VALIDATION_MATRIX_COLUMNS = (
    "bus_id",
    "bus_name",
    "screening_verdict",
    "qsts_short_verdict",
    "qsts_stratified_verdict",
    "qsts_full_year_verdict",
    "legacy_qsts_full_year_verdict",
    "selected_policy",
    "strict_policy_verdict",
    "standard_policy_verdict",
    "flexible_policy_verdict",
    "aggressive_policy_verdict",
    "final_decision",
    "calibration_status",
    "validation_level",
    "decision_confidence",
    "recommended_next_action",
    "qsts_short_p90_mw",
    "qsts_short_expected_mwh",
    "qsts_stratified_p90_mw",
    "qsts_stratified_expected_mwh",
    "qsts_full_year_p90_mw",
    "qsts_full_year_expected_mwh",
    "main_recurring_constraint",
)


@dataclass(frozen=True)
class ValidationMatrixRow:
    bus_id: int
    bus_name: str
    screening_verdict: str
    qsts_short_verdict: str
    qsts_stratified_verdict: str
    qsts_full_year_verdict: str
    legacy_qsts_full_year_verdict: str
    selected_policy: str
    strict_policy_verdict: str
    standard_policy_verdict: str
    flexible_policy_verdict: str
    aggressive_policy_verdict: str
    final_decision: str
    calibration_status: str
    validation_level: str
    decision_confidence: str
    recommended_next_action: str
    qsts_short_p90_mw: str
    qsts_short_expected_mwh: str
    qsts_stratified_p90_mw: str
    qsts_stratified_expected_mwh: str
    qsts_full_year_p90_mw: str
    qsts_full_year_expected_mwh: str
    main_recurring_constraint: str


@dataclass(frozen=True)
class ValidationMatrix:
    rows: tuple[ValidationMatrixRow, ...]


@dataclass(frozen=True)
class ValidationMatrixOutputPaths:
    csv_path: Path
    markdown_path: Path


def build_validation_matrix(
    screening_csv: Path,
    qsts_short_csv: Path | None = None,
    qsts_stratified_csv: Path | None = None,
    qsts_full_year_csvs: tuple[Path, ...] = (),
    decision_frontier_csvs: tuple[Path, ...] = (),
    selected_policy: str = "standard",
) -> ValidationMatrix:
    screening = _read_screening(screening_csv)
    short = _read_qsts(qsts_short_csv)
    stratified = _read_qsts(qsts_stratified_csv)
    full_year = _read_many_qsts(qsts_full_year_csvs)
    frontier = _read_many_frontier(decision_frontier_csvs)
    validated_bus_ids = set(short) | set(stratified) | set(full_year)
    bus_ids = sorted(validated_bus_ids or set(screening))
    rows = tuple(
        _build_row(
            bus_id=bus_id,
            screening=screening.get(bus_id, {}),
            short=short.get(bus_id, {}),
            stratified=stratified.get(bus_id, {}),
            full_year=full_year.get(bus_id, {}),
            frontier=frontier.get(bus_id, {}),
            selected_policy=selected_policy,
        )
        for bus_id in bus_ids
    )
    return ValidationMatrix(rows=rows)


def write_validation_matrix_outputs(
    matrix: ValidationMatrix,
    output_dir: Path,
) -> ValidationMatrixOutputPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "validation_matrix.csv"
    markdown_path = output_dir / "validation_matrix.md"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=VALIDATION_MATRIX_COLUMNS)
        writer.writeheader()
        for row in matrix.rows:
            writer.writerow(asdict(row))
    markdown_path.write_text(render_validation_matrix_markdown(matrix), encoding="utf-8")
    return ValidationMatrixOutputPaths(csv_path=csv_path, markdown_path=markdown_path)


def render_validation_matrix_markdown(matrix: ValidationMatrix) -> str:
    table = _render_rows(matrix.rows)
    false_positives = _render_bus_list(
        row
        for row in matrix.rows
        if row.calibration_status in {"false_positive_screening", "false_positive_stratified"}
    )
    requires_full_year = _render_bus_list(
        row for row in matrix.rows if row.calibration_status == "requires_full_year_validation"
    )
    changed = _render_bus_list(
        row for row in matrix.rows if row.calibration_status == "changed_after_full_year"
    )
    return f"""# Validation Matrix

This matrix compares static screening, short QSTS, stratified QSTS, and full-year QSTS.
`qsts_full_year` is the MVP investor reference, but it does not replace an official
grid-connection study.

## Decision Matrix

{table}

## False Positives

{false_positives}

## Requires Full-Year Validation

{requires_full_year}

## Other Full-Year Changes

{changed}
"""


def _build_row(
    bus_id: int,
    screening: dict[str, str],
    short: dict[str, str],
    stratified: dict[str, str],
    full_year: dict[str, str],
    frontier: dict[str, str],
    selected_policy: str,
) -> ValidationMatrixRow:
    strongest = full_year or stratified or short
    has_full_year = bool(full_year)
    policy_verdict = frontier.get(selected_policy, "")
    final_decision = (
        policy_verdict
        if has_full_year and policy_verdict
        else full_year.get("qsts_verdict", "requires_full_year_validation")
    )
    calibration_status = _calibration_status(
        screening,
        short,
        stratified,
        full_year,
        final_decision,
    )
    return ValidationMatrixRow(
        bus_id=bus_id,
        bus_name=_first_non_empty(
            full_year.get("bus_name", ""),
            stratified.get("bus_name", ""),
            short.get("bus_name", ""),
            screening.get("bus_name", ""),
        ),
        screening_verdict=screening.get("verdict", ""),
        qsts_short_verdict=short.get("qsts_verdict", ""),
        qsts_stratified_verdict=stratified.get("qsts_verdict", ""),
        qsts_full_year_verdict=full_year.get("qsts_verdict", ""),
        legacy_qsts_full_year_verdict=full_year.get("qsts_verdict", ""),
        selected_policy=selected_policy,
        strict_policy_verdict=frontier.get("strict", ""),
        standard_policy_verdict=frontier.get("standard", ""),
        flexible_policy_verdict=frontier.get("flexible", ""),
        aggressive_policy_verdict=frontier.get("aggressive", ""),
        final_decision=final_decision,
        calibration_status=calibration_status,
        validation_level=strongest.get(
            "validation_level",
            "qsts_full_year" if has_full_year else "screening_only",
        ),
        decision_confidence=strongest.get("decision_confidence", "high" if has_full_year else "low"),
        recommended_next_action=strongest.get(
            "recommended_next_action",
            "reject_or_resize_connection" if has_full_year else "run_qsts_validation",
        ),
        qsts_short_p90_mw=short.get("p90_curtailment_mw", ""),
        qsts_short_expected_mwh=_qsts_decision_mwh(short),
        qsts_stratified_p90_mw=stratified.get("p90_curtailment_mw", ""),
        qsts_stratified_expected_mwh=_qsts_decision_mwh(stratified),
        qsts_full_year_p90_mw=full_year.get("p90_curtailment_mw", ""),
        qsts_full_year_expected_mwh=_qsts_decision_mwh(full_year),
        main_recurring_constraint=_first_non_empty(
            full_year.get("main_recurring_constraint", ""),
            stratified.get("main_recurring_constraint", ""),
            short.get("main_recurring_constraint", ""),
        ),
    )


def _calibration_status(
    screening: dict[str, str],
    short: dict[str, str],
    stratified: dict[str, str],
    full_year: dict[str, str],
    final_decision: str | None = None,
) -> str:
    if not full_year:
        return "requires_full_year_validation"
    full_verdict = final_decision or full_year.get("qsts_verdict", "")
    stratified_verdict = stratified.get("qsts_verdict", "")
    short_verdict = short.get("qsts_verdict", "")
    screening_verdict = screening.get("verdict", "")
    if stratified_verdict == "go" and full_verdict == "no-go":
        return "false_positive_stratified"
    if screening_verdict in {"go", "go-with-conditions"} and full_verdict == "no-go":
        return "false_positive_screening"
    if stratified_verdict and stratified_verdict != full_verdict:
        return "changed_after_full_year"
    if short_verdict and short_verdict != full_verdict:
        return "changed_after_full_year"
    return "confirmed_full_year"


def _read_screening(path: Path) -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows[int(row["bus_id"])] = row
    return rows


def _read_qsts(path: Path | None) -> dict[int, dict[str, str]]:
    if path is None:
        return {}
    rows: dict[int, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows[int(row["bus_id"])] = row
    return rows


def _read_many_qsts(paths: tuple[Path, ...]) -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    for path in paths:
        for bus_id, row in _read_qsts(path).items():
            rows[bus_id] = row
    return rows


def _read_many_frontier(paths: tuple[Path, ...]) -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    for path in paths:
        if path is None:
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                bus_id = int(row["bus_id"])
                policy = row.get("policy", "")
                if not policy:
                    continue
                rows.setdefault(bus_id, {})[policy] = row.get("frontier_verdict", "")
    return rows


def _render_rows(rows: tuple[ValidationMatrixRow, ...]) -> str:
    if not rows:
        return "No validation rows available."
    lines = [
        "| bus_id | screening | short | stratified | full_year | final | status | next_action |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row.bus_id} | {row.screening_verdict or '-'} | "
            f"{row.qsts_short_verdict or '-'} | {row.qsts_stratified_verdict or '-'} | "
            f"{row.qsts_full_year_verdict or '-'} | {row.final_decision} | "
            f"{row.calibration_status} | {row.recommended_next_action} |"
        )
    return "\n".join(lines)


def _render_bus_list(rows: object) -> str:
    rendered = [
        f"- bus {row.bus_id} ({row.bus_name}): {row.calibration_status}, final={row.final_decision}"
        for row in rows
    ]
    return "\n".join(rendered) if rendered else "- None."


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def _qsts_decision_mwh(row: dict[str, str]) -> str:
    return _first_non_empty(
        row.get("weighted_curtailment_mwh", ""),
        row.get("expected_curtailment_mwh", ""),
    )
