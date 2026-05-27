import csv

from thesegrid.cli import main
from thesegrid.full_year_selection import (
    FullYearSelectionRequest,
    select_full_year_candidates,
    write_full_year_selection_csv,
)


def test_select_full_year_candidates_uses_top_borderline_suspect_and_control_buckets(tmp_path):
    screening = tmp_path / "screening.csv"
    stratified = tmp_path / "sensitivity_results.csv"
    validation = tmp_path / "validation_matrix.csv"
    _write_csv(
        screening,
        [
            "rank",
            "bus_id",
            "bus_name",
            "verdict",
            "evaluated_conditional_mw",
        ],
        [
            {"rank": "1", "bus_id": "2", "bus_name": "bus 2", "verdict": "go", "evaluated_conditional_mw": "5.0"},
            {"rank": "2", "bus_id": "3", "bus_name": "bus 3", "verdict": "go", "evaluated_conditional_mw": "5.0"},
            {"rank": "3", "bus_id": "16", "bus_name": "bus 16", "verdict": "go", "evaluated_conditional_mw": "5.0"},
            {"rank": "4", "bus_id": "21", "bus_name": "bus 21", "verdict": "no-go", "evaluated_conditional_mw": "5.0"},
            {"rank": "5", "bus_id": "24", "bus_name": "bus 24", "verdict": "no-go", "evaluated_conditional_mw": "5.0"},
            {"rank": "6", "bus_id": "17", "bus_name": "bus 17", "verdict": "go", "evaluated_conditional_mw": "5.0"},
        ],
    )
    _write_csv(
        stratified,
        [
            "bus_id",
            "bus_name",
            "qsts_verdict",
            "requested_mw",
            "qsts_p90_curtailment_mw",
            "qsts_expected_curtailment_mwh",
        ],
        [
            _stratified_row(3, "bus 3", "go", 7.0, 0.0, 0.0),
            _stratified_row(3, "bus 3", "go", 5.0, 0.0, 0.0),
            _stratified_row(16, "bus 16", "go", 7.0, 0.0, 0.0),
            _stratified_row(17, "bus 17", "go", 5.0, 0.0, 0.0),
            _stratified_row(21, "bus 21", "go-with-conditions", 3.0, 0.17, 4.2),
            _stratified_row(24, "bus 24", "no-go", 5.0, 2.6, 206.0),
        ],
    )
    _write_csv(
        validation,
        [
            "bus_id",
            "bus_name",
            "screening_verdict",
            "qsts_stratified_verdict",
            "qsts_stratified_p90_mw",
            "qsts_stratified_expected_mwh",
            "qsts_full_year_verdict",
            "calibration_status",
        ],
        [
            {
                "bus_id": "2",
                "bus_name": "bus 2",
                "screening_verdict": "go",
                "qsts_stratified_verdict": "go",
                "qsts_stratified_p90_mw": "0.0",
                "qsts_stratified_expected_mwh": "0.0",
                "qsts_full_year_verdict": "no-go",
                "calibration_status": "false_positive_stratified",
            }
        ],
    )

    candidates = select_full_year_candidates(
        FullYearSelectionRequest(
            screening_csv=screening,
            stratified_csv=stratified,
            validation_matrix_csv=validation,
            max_candidates=5,
            top_candidates=3,
            borderline_candidates=1,
            false_positive_suspects=1,
            bad_controls=1,
        )
    )

    assert [(candidate.bus_id, candidate.requested_mw) for candidate in candidates] == [
        (3, 7.0),
        (16, 7.0),
        (17, 5.0),
        (21, 3.0),
        (2, 0.0),
    ]
    assert [candidate.selection_bucket for candidate in candidates] == [
        "top_candidate",
        "top_candidate",
        "top_candidate",
        "borderline_candidate",
        "false_positive_suspect",
    ]


def test_select_full_year_candidates_defaults_to_small_balanced_finalist_set(tmp_path):
    screening = tmp_path / "screening.csv"
    stratified = tmp_path / "sensitivity_results.csv"
    _write_csv(
        screening,
        [
            "rank",
            "bus_id",
            "bus_name",
            "verdict",
            "evaluated_conditional_mw",
        ],
        [
            {"rank": "1", "bus_id": "2", "bus_name": "bus 2", "verdict": "go", "evaluated_conditional_mw": "5.0"},
            {"rank": "2", "bus_id": "3", "bus_name": "bus 3", "verdict": "go", "evaluated_conditional_mw": "5.0"},
            {"rank": "3", "bus_id": "16", "bus_name": "bus 16", "verdict": "go", "evaluated_conditional_mw": "5.0"},
            {"rank": "4", "bus_id": "21", "bus_name": "bus 21", "verdict": "go-with-conditions", "evaluated_conditional_mw": "4.8"},
            {"rank": "5", "bus_id": "22", "bus_name": "bus 22", "verdict": "go-with-conditions", "evaluated_conditional_mw": "4.6"},
            {"rank": "6", "bus_id": "24", "bus_name": "bus 24", "verdict": "no-go", "evaluated_conditional_mw": "4.0"},
        ],
    )
    _write_csv(
        stratified,
        [
            "bus_id",
            "bus_name",
            "qsts_verdict",
            "requested_mw",
            "qsts_p90_curtailment_mw",
            "qsts_expected_curtailment_mwh",
        ],
        [
            _stratified_row(2, "bus 2", "go", 5.0, 0.0, 0.0),
            _stratified_row(3, "bus 3", "go", 5.0, 0.0, 0.0),
            _stratified_row(16, "bus 16", "go", 5.0, 0.0, 0.0),
            _stratified_row(21, "bus 21", "go-with-conditions", 5.0, 0.4, 12.0),
            _stratified_row(22, "bus 22", "go-with-conditions", 5.0, 0.6, 20.0),
            _stratified_row(24, "bus 24", "no-go", 5.0, 2.6, 206.0),
        ],
    )

    candidates = select_full_year_candidates(
        FullYearSelectionRequest(screening_csv=screening, stratified_csv=stratified)
    )

    assert len(candidates) == 5
    assert [candidate.selection_bucket for candidate in candidates] == [
        "top_candidate",
        "top_candidate",
        "borderline_candidate",
        "borderline_candidate",
        "bad_control",
    ]
    assert [candidate.bus_id for candidate in candidates] == [2, 3, 21, 22, 24]


def test_write_full_year_selection_csv_writes_candidates(tmp_path):
    screening = tmp_path / "screening.csv"
    _write_csv(
        screening,
        ["rank", "bus_id", "bus_name", "verdict", "evaluated_conditional_mw"],
        [{"rank": "1", "bus_id": "3", "bus_name": "bus 3", "verdict": "go", "evaluated_conditional_mw": "5.0"}],
    )
    candidates = select_full_year_candidates(
        FullYearSelectionRequest(screening_csv=screening, max_candidates=1)
    )

    output = write_full_year_selection_csv(candidates, tmp_path / "selection.csv")

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["bus_id"] == "3"
    assert rows[0]["selection_bucket"] == "screening_fallback"


def test_select_full_year_candidates_cli_writes_csv(tmp_path):
    screening = tmp_path / "screening.csv"
    _write_csv(
        screening,
        ["rank", "bus_id", "bus_name", "verdict", "evaluated_conditional_mw"],
        [{"rank": "1", "bus_id": "3", "bus_name": "bus 3", "verdict": "go", "evaluated_conditional_mw": "5.0"}],
    )
    output = tmp_path / "selection.csv"

    exit_code = main(
        [
            "select-full-year-candidates",
            "--screening-csv",
            str(screening),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["bus_id"] == "3"


def _stratified_row(bus_id, bus_name, verdict, requested_mw, p90_mw, expected_mwh):
    return {
        "bus_id": str(bus_id),
        "bus_name": bus_name,
        "qsts_verdict": verdict,
        "requested_mw": f"{requested_mw:.6f}",
        "qsts_p90_curtailment_mw": f"{p90_mw:.6f}",
        "qsts_expected_curtailment_mwh": f"{expected_mwh:.6f}",
    }


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
