import csv

from thesegrid.cli import main
from thesegrid.stratified_selection import (
    StratifiedSelectionRequest,
    select_stratified_candidates,
    write_stratified_selection_csv,
)


def test_select_stratified_candidates_defaults_to_balanced_shortlist(tmp_path):
    screening = tmp_path / "screening.csv"
    _write_screening(
        screening,
        [
            _row(1, 2, "go", 5.0, 5.0, 0.0, "none"),
            _row(2, 3, "go", 5.0, 5.0, 0.0, "none"),
            _row(3, 16, "go", 5.0, 5.0, 0.0, "none"),
            _row(4, 17, "go", 5.0, 5.0, 0.0, "none"),
            _row(5, 18, "go", 5.0, 5.0, 0.0, "none"),
            _row(6, 19, "go", 5.0, 5.0, 0.0, "none"),
            _row(7, 21, "go-with-conditions", 4.8, 4.8, 0.2, "bus[20] voltage"),
            _row(8, 22, "go-with-conditions", 4.7, 4.7, 0.4, "line[0] loading"),
            _row(9, 23, "go-with-conditions", 4.6, 4.6, 0.6, "trafo[0] loading"),
            _row(10, 24, "go-with-conditions", 4.5, 4.5, 0.8, "bus[15] voltage"),
            _row(11, 25, "no-go", 4.4, 4.4, 1.0, "bus[20] voltage"),
            _row(12, 26, "no-go", 4.3, 4.3, 1.2, "line[0] loading"),
            _row(13, 27, "no-go", 3.8, 3.8, 2.0, "bus[30] voltage"),
            _row(14, 28, "no-go", 3.6, 3.6, 2.2, "line[9] loading"),
        ],
    )

    candidates = select_stratified_candidates(StratifiedSelectionRequest(screening_csv=screening))

    assert len(candidates) == 12
    assert [candidate.selection_bucket for candidate in candidates] == [
        "top_go",
        "top_go",
        "top_go",
        "top_go",
        "top_go",
        "borderline",
        "borderline",
        "borderline",
        "near_threshold_no_go",
        "near_threshold_no_go",
        "constraint_diverse",
        "constraint_diverse",
    ]
    assert [candidate.bus_id for candidate in candidates] == [2, 3, 16, 17, 18, 21, 22, 23, 25, 26, 27, 28]


def test_write_stratified_selection_csv_writes_bus_ids(tmp_path):
    screening = tmp_path / "screening.csv"
    _write_screening(screening, [_row(1, 2, "go", 5.0, 5.0, 0.0, "none")])
    candidates = select_stratified_candidates(
        StratifiedSelectionRequest(screening_csv=screening, max_candidates=1)
    )

    output = write_stratified_selection_csv(candidates, tmp_path / "selection.csv")

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["bus_id"] == "2"
    assert rows[0]["selection_bucket"] == "top_go"


def test_select_stratified_candidates_cli_writes_csv(tmp_path):
    screening = tmp_path / "screening.csv"
    _write_screening(screening, [_row(1, 2, "go", 5.0, 5.0, 0.0, "none")])
    output = tmp_path / "selection.csv"

    exit_code = main(
        [
            "select-stratified-candidates",
            "--screening-csv",
            str(screening),
            "--output",
            str(output),
            "--max-candidates",
            "1",
        ]
    )

    assert exit_code == 0
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["bus_id"] == "2"


def _row(
    rank,
    bus_id,
    verdict,
    firm_capacity_mw,
    conditional_capacity_mw,
    p90_curtailment_mw,
    main_constraint,
):
    return {
        "rank": str(rank),
        "bus_id": str(bus_id),
        "bus_name": f"bus {bus_id}",
        "verdict": verdict,
        "firm_capacity_mw": f"{firm_capacity_mw:.6f}",
        "conditional_capacity_mw": f"{conditional_capacity_mw:.6f}",
        "evaluated_conditional_mw": f"{conditional_capacity_mw:.6f}",
        "p90_curtailment_mw": f"{p90_curtailment_mw:.6f}",
        "main_constraint": main_constraint,
    }


def _write_screening(path, rows):
    fieldnames = [
        "rank",
        "bus_id",
        "bus_name",
        "verdict",
        "firm_capacity_mw",
        "conditional_capacity_mw",
        "evaluated_conditional_mw",
        "p90_curtailment_mw",
        "main_constraint",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
