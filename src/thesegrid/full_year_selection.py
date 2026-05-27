from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_FULL_YEAR_MAX_CANDIDATES = 5
DEFAULT_FULL_YEAR_TOP_CANDIDATES = 2
DEFAULT_FULL_YEAR_BORDERLINE_CANDIDATES = 2
DEFAULT_FULL_YEAR_FALSE_POSITIVE_SUSPECTS = 0
DEFAULT_FULL_YEAR_BAD_CONTROLS = 1


@dataclass(frozen=True)
class FullYearSelectionRequest:
    screening_csv: Path
    stratified_csv: Path | None = None
    validation_matrix_csv: Path | None = None
    max_candidates: int = DEFAULT_FULL_YEAR_MAX_CANDIDATES
    top_candidates: int = DEFAULT_FULL_YEAR_TOP_CANDIDATES
    borderline_candidates: int = DEFAULT_FULL_YEAR_BORDERLINE_CANDIDATES
    false_positive_suspects: int = DEFAULT_FULL_YEAR_FALSE_POSITIVE_SUSPECTS
    bad_controls: int = DEFAULT_FULL_YEAR_BAD_CONTROLS

    def __post_init__(self) -> None:
        if self.max_candidates <= 0:
            raise ValueError("max_candidates must be positive")
        for name in (
            "top_candidates",
            "borderline_candidates",
            "false_positive_suspects",
            "bad_controls",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class FullYearCandidate:
    bus_id: int
    bus_name: str
    requested_mw: float
    selection_bucket: str
    selection_reason: str
    screening_rank: int | None
    screening_verdict: str
    stratified_verdict: str
    stratified_p90_mw: float | None
    stratified_expected_mwh: float | None


def select_full_year_candidates(request: FullYearSelectionRequest) -> tuple[FullYearCandidate, ...]:
    screening_rows = _read_csv(request.screening_csv)
    stratified_rows = _read_csv(request.stratified_csv)
    validation_rows = _read_csv(request.validation_matrix_csv)
    full_year_bus_ids = {
        int(row["bus_id"])
        for row in validation_rows
        if row.get("bus_id") and row.get("qsts_full_year_verdict")
    }

    selected: list[FullYearCandidate] = []
    seen: set[tuple[int, float]] = set()
    seen_bus_ids: set[int] = set()

    def add(row: dict[str, str], bucket: str, reason: str) -> None:
        if len(selected) >= request.max_candidates:
            return
        candidate = _candidate_from_row(row, bucket, reason, screening_rows)
        if candidate is None:
            return
        key = (candidate.bus_id, candidate.requested_mw)
        if key in seen or candidate.bus_id in seen_bus_ids:
            return
        seen.add(key)
        seen_bus_ids.add(candidate.bus_id)
        selected.append(candidate)

    top_rows = [
        row
        for row in stratified_rows
        if row.get("qsts_verdict") == "go" and int(row.get("bus_id", -1)) not in full_year_bus_ids
    ]
    top_rows = sorted(
        top_rows,
        key=lambda row: (
            -_float(row.get("requested_mw")),
            _screening_rank(row, screening_rows),
            int(row.get("bus_id", 0)),
        ),
    )
    added_top = 0
    for row in top_rows:
        before = len(selected)
        add(row, "top_candidate", "stratified go at highest tested MW")
        if len(selected) > before:
            added_top += 1
        if added_top >= request.top_candidates:
            break

    borderline_rows = [
        row
        for row in stratified_rows
        if row.get("qsts_verdict") == "go-with-conditions"
        and int(row.get("bus_id", -1)) not in full_year_bus_ids
    ]
    borderline_rows = sorted(
        borderline_rows,
        key=lambda row: (
            _float(row.get("qsts_expected_curtailment_mwh")),
            _float(row.get("qsts_p90_curtailment_mw")),
            -_float(row.get("requested_mw")),
        ),
    )
    added_borderline = 0
    for row in borderline_rows:
        before = len(selected)
        add(row, "borderline_candidate", "stratified go-with-conditions needs full-year check")
        if len(selected) > before:
            added_borderline += 1
        if added_borderline >= request.borderline_candidates:
            break

    suspect_rows = [
        row
        for row in validation_rows
        if row.get("calibration_status") in {"false_positive_screening", "false_positive_stratified"}
    ]
    suspect_rows = sorted(suspect_rows, key=lambda row: int(row.get("bus_id", 0)))
    for row in suspect_rows[: request.false_positive_suspects]:
        if len(selected) >= request.max_candidates:
            break
        candidate = _candidate_from_validation_row(
            row,
            bucket="false_positive_suspect",
            reason="existing validation false positive; test adjacent or higher MW separately",
        )
        key = (candidate.bus_id, candidate.requested_mw)
        if key not in seen and candidate.bus_id not in seen_bus_ids:
            seen.add(key)
            seen_bus_ids.add(candidate.bus_id)
            selected.append(candidate)

    bad_rows = [
        row
        for row in stratified_rows
        if row.get("qsts_verdict") == "no-go" and int(row.get("bus_id", -1)) not in full_year_bus_ids
    ]
    bad_rows = sorted(
        bad_rows,
        key=lambda row: (
            -_float(row.get("qsts_expected_curtailment_mwh")),
            -_float(row.get("requested_mw")),
        ),
    )
    added_bad = 0
    for row in bad_rows:
        before = len(selected)
        add(row, "bad_control", "high-risk stratified no-go for calibration control")
        if len(selected) > before:
            added_bad += 1
        if added_bad >= request.bad_controls:
            break

    if len(selected) < request.max_candidates:
        fallback_rows = [
            row
            for row in screening_rows
            if row.get("verdict") == "go" and int(row.get("bus_id", -1)) not in full_year_bus_ids
        ]
        fallback_rows = sorted(fallback_rows, key=lambda row: int(row.get("rank", 999999)))
        for row in fallback_rows:
            if len(selected) >= request.max_candidates:
                break
            add(
                _screening_as_candidate_row(row),
                "screening_fallback",
                "high-ranked screening go not yet validated in full-year",
            )

    return tuple(selected)


def write_full_year_selection_csv(
    candidates: tuple[FullYearCandidate, ...],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(candidates[0]).keys()))
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(asdict(candidate))
    return output_path


def _candidate_from_row(
    row: dict[str, str],
    bucket: str,
    reason: str,
    screening_rows: list[dict[str, str]],
) -> FullYearCandidate | None:
    bus_id_text = row.get("bus_id")
    requested_mw = _float(row.get("requested_mw"))
    if not bus_id_text or requested_mw <= 0:
        return None
    bus_id = int(bus_id_text)
    screening = _screening_by_bus(screening_rows).get(bus_id, {})
    return FullYearCandidate(
        bus_id=bus_id,
        bus_name=row.get("bus_name", screening.get("bus_name", "")),
        requested_mw=requested_mw,
        selection_bucket=bucket,
        selection_reason=reason,
        screening_rank=int(screening["rank"]) if screening.get("rank") else None,
        screening_verdict=screening.get("verdict", ""),
        stratified_verdict=row.get("qsts_verdict", ""),
        stratified_p90_mw=_optional_float(row.get("qsts_p90_curtailment_mw")),
        stratified_expected_mwh=_optional_float(row.get("qsts_expected_curtailment_mwh")),
    )


def _candidate_from_validation_row(
    row: dict[str, str],
    bucket: str,
    reason: str,
) -> FullYearCandidate:
    return FullYearCandidate(
        bus_id=int(row["bus_id"]),
        bus_name=row.get("bus_name", ""),
        requested_mw=0.0,
        selection_bucket=bucket,
        selection_reason=reason,
        screening_rank=None,
        screening_verdict=row.get("screening_verdict", ""),
        stratified_verdict=row.get("qsts_stratified_verdict", ""),
        stratified_p90_mw=_optional_float(row.get("qsts_stratified_p90_mw")),
        stratified_expected_mwh=_optional_float(row.get("qsts_stratified_expected_mwh")),
    )


def _screening_as_candidate_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "bus_id": row.get("bus_id", ""),
        "bus_name": row.get("bus_name", ""),
        "requested_mw": row.get("evaluated_conditional_mw", ""),
        "qsts_verdict": "",
        "qsts_p90_curtailment_mw": "",
        "qsts_expected_curtailment_mwh": "",
    }


def _read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _screening_by_bus(rows: list[dict[str, str]]) -> dict[int, dict[str, str]]:
    return {int(row["bus_id"]): row for row in rows if row.get("bus_id")}


def _screening_rank(row: dict[str, str], screening_rows: list[dict[str, str]]) -> int:
    screening = _screening_by_bus(screening_rows).get(int(row.get("bus_id", -1)), {})
    return int(screening.get("rank", 999999))


def _float(value: str | None) -> float:
    if value in {None, ""}:
        return 0.0
    return float(value)


def _optional_float(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)
