from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_STRATIFIED_MAX_CANDIDATES = 12
DEFAULT_STRATIFIED_TOP_GO_CANDIDATES = 5
DEFAULT_STRATIFIED_BORDERLINE_CANDIDATES = 3
DEFAULT_STRATIFIED_NEAR_THRESHOLD_NO_GO_CANDIDATES = 2
DEFAULT_STRATIFIED_CONSTRAINT_DIVERSE_CANDIDATES = 2

STRATIFIED_SELECTION_COLUMNS = (
    "bus_id",
    "bus_name",
    "selection_bucket",
    "selection_reason",
    "screening_rank",
    "screening_verdict",
    "firm_capacity_mw",
    "conditional_capacity_mw",
    "evaluated_conditional_mw",
    "p90_curtailment_mw",
    "main_constraint",
)


@dataclass(frozen=True)
class StratifiedSelectionRequest:
    screening_csv: Path
    max_candidates: int = DEFAULT_STRATIFIED_MAX_CANDIDATES
    top_go_candidates: int = DEFAULT_STRATIFIED_TOP_GO_CANDIDATES
    borderline_candidates: int = DEFAULT_STRATIFIED_BORDERLINE_CANDIDATES
    near_threshold_no_go_candidates: int = DEFAULT_STRATIFIED_NEAR_THRESHOLD_NO_GO_CANDIDATES
    constraint_diverse_candidates: int = DEFAULT_STRATIFIED_CONSTRAINT_DIVERSE_CANDIDATES

    def __post_init__(self) -> None:
        if self.max_candidates <= 0:
            raise ValueError("max_candidates must be positive")
        for name in (
            "top_go_candidates",
            "borderline_candidates",
            "near_threshold_no_go_candidates",
            "constraint_diverse_candidates",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class StratifiedCandidate:
    bus_id: int
    bus_name: str
    selection_bucket: str
    selection_reason: str
    screening_rank: int | None
    screening_verdict: str
    firm_capacity_mw: float | None
    conditional_capacity_mw: float | None
    evaluated_conditional_mw: float | None
    p90_curtailment_mw: float | None
    main_constraint: str


def select_stratified_candidates(
    request: StratifiedSelectionRequest,
) -> tuple[StratifiedCandidate, ...]:
    rows = _read_csv(request.screening_csv)
    selected: list[StratifiedCandidate] = []
    seen_bus_ids: set[int] = set()

    def add(row: dict[str, str], bucket: str, reason: str) -> bool:
        if len(selected) >= request.max_candidates:
            return False
        candidate = _candidate_from_row(row, bucket, reason)
        if candidate is None or candidate.bus_id in seen_bus_ids:
            return False
        selected.append(candidate)
        seen_bus_ids.add(candidate.bus_id)
        return True

    _add_limited(
        selected=selected,
        rows=sorted(
            (row for row in rows if row.get("verdict") == "go"),
            key=lambda row: _int(row.get("rank"), default=999999),
        ),
        limit=request.top_go_candidates,
        add=lambda row: add(row, "top_go", "best screening go candidates"),
    )

    _add_limited(
        selected=selected,
        rows=sorted(
            (row for row in rows if row.get("verdict") == "go-with-conditions"),
            key=lambda row: (
                -_float(row.get("conditional_capacity_mw")),
                _float(row.get("p90_curtailment_mw")),
                _int(row.get("rank"), default=999999),
            ),
        ),
        limit=request.borderline_candidates,
        add=lambda row: add(row, "borderline", "screening go-with-conditions needs QSTS check"),
    )

    _add_limited(
        selected=selected,
        rows=sorted(
            (row for row in rows if row.get("verdict") == "no-go"),
            key=lambda row: (
                -_float(row.get("conditional_capacity_mw")),
                -_float(row.get("firm_capacity_mw")),
                _float(row.get("p90_curtailment_mw")),
                _int(row.get("rank"), default=999999),
            ),
        ),
        limit=request.near_threshold_no_go_candidates,
        add=lambda row: add(row, "near_threshold_no_go", "screening no-go closest to requested MW"),
    )

    diverse_rows = _constraint_diverse_rows(rows, seen_bus_ids)
    _add_limited(
        selected=selected,
        rows=diverse_rows,
        limit=request.constraint_diverse_candidates,
        add=lambda row: add(row, "constraint_diverse", "adds a distinct recurring constraint family"),
    )

    if len(selected) < request.max_candidates:
        fallback_rows = sorted(rows, key=lambda row: _int(row.get("rank"), default=999999))
        for row in fallback_rows:
            if len(selected) >= request.max_candidates:
                break
            add(row, "screening_fallback", "fills remaining stratified shortlist capacity")

    return tuple(selected)


def write_stratified_selection_csv(
    candidates: tuple[StratifiedCandidate, ...],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=STRATIFIED_SELECTION_COLUMNS)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    column: asdict(candidate)[column]
                    for column in STRATIFIED_SELECTION_COLUMNS
                }
            )
    return output_path


def _add_limited(
    *,
    selected: list[StratifiedCandidate],
    rows: list[dict[str, str]],
    limit: int,
    add,
) -> None:
    added = 0
    for row in rows:
        if added >= limit:
            break
        before = len(selected)
        if add(row) and len(selected) > before:
            added += 1


def _candidate_from_row(
    row: dict[str, str],
    bucket: str,
    reason: str,
) -> StratifiedCandidate | None:
    if not row.get("bus_id"):
        return None
    return StratifiedCandidate(
        bus_id=int(row["bus_id"]),
        bus_name=row.get("bus_name", ""),
        selection_bucket=bucket,
        selection_reason=reason,
        screening_rank=_optional_int(row.get("rank")),
        screening_verdict=row.get("verdict", ""),
        firm_capacity_mw=_optional_float(row.get("firm_capacity_mw")),
        conditional_capacity_mw=_optional_float(row.get("conditional_capacity_mw")),
        evaluated_conditional_mw=_optional_float(row.get("evaluated_conditional_mw")),
        p90_curtailment_mw=_optional_float(row.get("p90_curtailment_mw")),
        main_constraint=row.get("main_constraint", ""),
    )


def _constraint_diverse_rows(
    rows: list[dict[str, str]],
    seen_bus_ids: set[int],
) -> list[dict[str, str]]:
    diverse: list[dict[str, str]] = []
    seen_constraints: set[str] = set()
    no_go = [row for row in rows if row.get("verdict") == "no-go"]
    other = [row for row in rows if row.get("verdict") != "no-go"]
    candidates = [
        *sorted(no_go, key=lambda row: _int(row.get("rank"), default=999999)),
        *sorted(other, key=lambda row: _int(row.get("rank"), default=999999)),
    ]
    for row in candidates:
        bus_id = _optional_int(row.get("bus_id"))
        if bus_id is None or bus_id in seen_bus_ids:
            continue
        key = _constraint_family(row.get("main_constraint", ""))
        if not key or key in {"none", "no_binding_constraint"} or key in seen_constraints:
            continue
        seen_constraints.add(key)
        diverse.append(row)
    return diverse


def _constraint_family(value: str) -> str:
    text = value.strip().lower()
    if not text:
        return ""
    return re.sub(r"\s+", " ", text)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _optional_float(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _float(value: str | None) -> float:
    return _optional_float(value) or 0.0


def _optional_int(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def _int(value: str | None, *, default: int) -> int:
    return _optional_int(value) if value not in {None, ""} else default
