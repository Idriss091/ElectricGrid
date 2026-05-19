import csv
from pathlib import Path

from thesegrid.cli import main
from thesegrid.validation_matrix import (
    build_validation_matrix,
    render_validation_matrix_markdown,
    write_validation_matrix_outputs,
)


def test_validation_matrix_uses_full_year_as_final_decision_and_marks_false_positive(tmp_path):
    screening = tmp_path / "screening.csv"
    qsts_short = tmp_path / "qsts_short.csv"
    qsts_stratified = tmp_path / "qsts_stratified.csv"
    qsts_full_year = tmp_path / "qsts_full_year.csv"
    _write_screening(screening)
    _write_qsts(
        qsts_short,
        [
            _qsts_row(2, "go", "qsts_short", "low", "run_full_year_validation", 0.0, 0.0),
            _qsts_row(
                21,
                "go-with-conditions",
                "qsts_short",
                "low",
                "run_full_year_validation",
                2.1,
                45.0,
            ),
        ],
    )
    _write_qsts(
        qsts_stratified,
        [
            _qsts_row(2, "go", "qsts_stratified", "medium", "run_full_year_validation", 0.0, 0.0),
            _qsts_row(
                21,
                "no-go",
                "qsts_stratified",
                "medium",
                "resize_or_run_full_year_validation",
                2.2,
                166.0,
            ),
        ],
    )
    _write_qsts(
        qsts_full_year,
        [
            _qsts_row(
                2,
                "no-go",
                "qsts_full_year",
                "high",
                "reject_or_resize_connection",
                0.0,
                121.0,
            ),
        ],
    )

    matrix = build_validation_matrix(
        screening_csv=screening,
        qsts_short_csv=qsts_short,
        qsts_stratified_csv=qsts_stratified,
        qsts_full_year_csvs=(qsts_full_year,),
    )

    bus2 = next(row for row in matrix.rows if row.bus_id == 2)
    assert bus2.screening_verdict == "go"
    assert bus2.qsts_stratified_verdict == "go"
    assert bus2.qsts_full_year_verdict == "no-go"
    assert bus2.validation_level == "qsts_full_year"
    assert bus2.decision_confidence == "high"
    assert bus2.recommended_next_action == "reject_or_resize_connection"
    assert bus2.final_decision == "no-go"
    assert bus2.calibration_status == "false_positive_stratified"

    bus21 = next(row for row in matrix.rows if row.bus_id == 21)
    assert bus21.qsts_full_year_verdict == ""
    assert bus21.final_decision == "requires_full_year_validation"
    assert bus21.calibration_status == "requires_full_year_validation"


def test_validation_matrix_outputs_csv_and_markdown(tmp_path):
    screening = tmp_path / "screening.csv"
    qsts_short = tmp_path / "qsts_short.csv"
    qsts_stratified = tmp_path / "qsts_stratified.csv"
    qsts_full_year = tmp_path / "qsts_full_year.csv"
    output = tmp_path / "matrix"
    _write_screening(screening)
    _write_qsts(qsts_short, [_qsts_row(2, "go", "qsts_short", "low", "run_full_year_validation", 0.0, 0.0)])
    _write_qsts(
        qsts_stratified,
        [_qsts_row(2, "go", "qsts_stratified", "medium", "run_full_year_validation", 0.0, 0.0)],
    )
    _write_qsts(
        qsts_full_year,
        [_qsts_row(2, "no-go", "qsts_full_year", "high", "reject_or_resize_connection", 0.0, 121.0)],
    )

    outputs = write_validation_matrix_outputs(
        build_validation_matrix(
            screening_csv=screening,
            qsts_short_csv=qsts_short,
            qsts_stratified_csv=qsts_stratified,
            qsts_full_year_csvs=(qsts_full_year,),
        ),
        output,
    )

    assert outputs.csv_path.exists()
    assert outputs.markdown_path.exists()
    rows = list(csv.DictReader(outputs.csv_path.open(encoding="utf-8")))
    assert rows[0]["calibration_status"] == "false_positive_stratified"
    markdown = outputs.markdown_path.read_text(encoding="utf-8")
    assert "Validation Matrix" in markdown
    assert "False Positives" in markdown
    assert "bus 2" in markdown


def test_validation_matrix_omits_screening_only_rows_when_qsts_evidence_exists(tmp_path):
    screening = tmp_path / "screening.csv"
    qsts_short = tmp_path / "qsts_short.csv"
    _write_screening(screening)
    _write_qsts(qsts_short, [_qsts_row(2, "go", "qsts_short", "low", "run_full_year_validation", 0.0, 0.0)])

    matrix = build_validation_matrix(
        screening_csv=screening,
        qsts_short_csv=qsts_short,
        qsts_stratified_csv=None,
        qsts_full_year_csvs=(),
    )

    assert [row.bus_id for row in matrix.rows] == [2]


def test_compare_validation_cli_writes_outputs(tmp_path):
    screening = tmp_path / "screening.csv"
    qsts_short = tmp_path / "qsts_short.csv"
    qsts_stratified = tmp_path / "qsts_stratified.csv"
    qsts_full_year = tmp_path / "qsts_full_year.csv"
    output = tmp_path / "out"
    _write_screening(screening)
    _write_qsts(qsts_short, [_qsts_row(2, "go", "qsts_short", "low", "run_full_year_validation", 0.0, 0.0)])
    _write_qsts(
        qsts_stratified,
        [_qsts_row(2, "go", "qsts_stratified", "medium", "run_full_year_validation", 0.0, 0.0)],
    )
    _write_qsts(
        qsts_full_year,
        [_qsts_row(2, "no-go", "qsts_full_year", "high", "reject_or_resize_connection", 0.0, 121.0)],
    )

    exit_code = main(
        [
            "compare-validation",
            "--screening-csv",
            str(screening),
            "--qsts-short",
            str(qsts_short),
            "--qsts-stratified",
            str(qsts_stratified),
            "--qsts-full-year",
            str(qsts_full_year),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert (output / "validation_matrix.csv").exists()
    assert (output / "validation_matrix.md").exists()


def test_validation_matrix_markdown_reports_missing_full_year(tmp_path):
    screening = tmp_path / "screening.csv"
    qsts_short = tmp_path / "qsts_short.csv"
    qsts_stratified = tmp_path / "qsts_stratified.csv"
    _write_screening(screening)
    _write_qsts(qsts_short, [_qsts_row(21, "go-with-conditions", "qsts_short", "low", "run_full_year_validation", 2.1, 45.0)])
    _write_qsts(
        qsts_stratified,
        [
            _qsts_row(
                21,
                "no-go",
                "qsts_stratified",
                "medium",
                "resize_or_run_full_year_validation",
                2.2,
                166.0,
            )
        ],
    )

    matrix = build_validation_matrix(
        screening_csv=screening,
        qsts_short_csv=qsts_short,
        qsts_stratified_csv=qsts_stratified,
        qsts_full_year_csvs=(),
    )

    markdown = render_validation_matrix_markdown(matrix)

    assert "Requires Full-Year Validation" in markdown
    assert "bus 21" in markdown


def test_validation_matrix_marks_screening_false_positive_without_stratified_evidence(tmp_path):
    screening = tmp_path / "screening.csv"
    qsts_full_year = tmp_path / "qsts_full_year.csv"
    _write_screening(screening)
    _write_qsts(
        qsts_full_year,
        [
            _qsts_row(
                2,
                "no-go",
                "qsts_full_year",
                "high",
                "reject_or_resize_connection",
                0.0,
                121.0,
            )
        ],
    )

    matrix = build_validation_matrix(
        screening_csv=screening,
        qsts_short_csv=None,
        qsts_stratified_csv=None,
        qsts_full_year_csvs=(qsts_full_year,),
    )

    bus2 = next(row for row in matrix.rows if row.bus_id == 2)
    assert bus2.screening_verdict == "go"
    assert bus2.qsts_full_year_verdict == "no-go"
    assert bus2.final_decision == "no-go"
    assert bus2.calibration_status == "false_positive_screening"


def _write_screening(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["rank", "bus_id", "bus_name", "verdict"],
        )
        writer.writeheader()
        writer.writerow({"rank": "1", "bus_id": "2", "bus_name": "bus 2", "verdict": "go"})
        writer.writerow({"rank": "45", "bus_id": "21", "bus_name": "bus 21", "verdict": "no-go"})


def _write_qsts(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "rank",
            "bus_id",
            "bus_name",
            "qsts_verdict",
            "validation_level",
            "decision_confidence",
            "recommended_next_action",
            "p90_curtailment_mw",
            "expected_curtailment_mwh",
            "main_recurring_constraint",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _qsts_row(
    bus_id: int,
    verdict: str,
    level: str,
    confidence: str,
    action: str,
    p90_mw: float,
    mwh: float,
) -> dict[str, str]:
    return {
        "rank": "1",
        "bus_id": str(bus_id),
        "bus_name": f"bus {bus_id}",
        "qsts_verdict": verdict,
        "validation_level": level,
        "decision_confidence": confidence,
        "recommended_next_action": action,
        "p90_curtailment_mw": f"{p90_mw:.6f}",
        "expected_curtailment_mwh": f"{mwh:.6f}",
        "main_recurring_constraint": "",
    }
