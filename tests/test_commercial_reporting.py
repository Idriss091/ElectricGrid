from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from thesegrid.commercial_reporting import run_commercial_validation
from thesegrid.commercial_validation import (
    GROUND_TRUTH_COLUMNS,
    INTERVIEW_COLUMNS,
    PILOT_COLUMNS,
)


def _write_header(path: Path, columns: tuple[str, ...]) -> None:
    path.write_text(",".join(columns) + "\n", encoding="utf-8")


def _append_row(path: Path, columns: tuple[str, ...], values: dict[str, str]) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writerow(values)


def test_commercial_validation_writes_auditable_empty_evidence_bundle(tmp_path: Path):
    interviews = tmp_path / "interviews.csv"
    pilots = tmp_path / "pilots.csv"
    ground_truth = tmp_path / "ground_truth.csv"
    output = tmp_path / "output"
    _write_header(interviews, INTERVIEW_COLUMNS)
    _write_header(pilots, PILOT_COLUMNS)
    _write_header(ground_truth, GROUND_TRUTH_COLUMNS)

    result = run_commercial_validation(
        interviews_path=interviews,
        pilots_path=pilots,
        ground_truth_path=ground_truth,
        output_dir=output,
        now=lambda: datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
    )

    assert result.summary_path.exists()
    assert result.report_path.exists()
    assert result.interview_metrics_path.exists()
    assert result.pilot_metrics_path.exists()
    assert result.calibration_metrics_path.exists()
    assert result.manifest_path.exists()

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["overall_decision"] == "insufficient_evidence"
    assert summary["interviews"]["completed_interview_count"] == 0
    assert summary["interviews"]["decision"] == "insufficient_evidence"
    assert summary["pilots"]["pilot_count"] == 0
    assert summary["ground_truth"]["site_count"] == 0
    assert summary["ground_truth"]["precision"] is None
    assert summary["remaining_external_actions"]

    report = result.report_path.read_text(encoding="utf-8")
    assert "# VoltPath Commercial Validation" in report
    assert "insufficient_evidence" in report
    assert "No customer, payment, or grid-study outcome is inferred" in report

    with result.interview_metrics_path.open(newline="", encoding="utf-8") as handle:
        interview_rows = list(csv.DictReader(handle))
    by_metric = {row["metric"]: row for row in interview_rows}
    assert by_metric["completed_interviews"]["threshold"] == ">= 12"
    assert by_metric["completed_interviews"]["status"] == "not_measured"

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["created_at_utc"] == "2026-06-11T12:00:00+00:00"
    assert len(manifest["input_manifests"]) == 3
    assert all(len(source["sha256"]) == 64 for source in manifest["input_manifests"])
    assert all(source["row_count"] == 0 for source in manifest["input_manifests"])
    assert manifest["outputs"]["summary"] == "commercial_validation_summary.json"


def test_observed_zero_metrics_are_failures_not_missing_evidence(tmp_path: Path):
    interviews = tmp_path / "interviews.csv"
    pilots = tmp_path / "pilots.csv"
    ground_truth = tmp_path / "ground_truth.csv"
    output = tmp_path / "output"
    _write_header(interviews, INTERVIEW_COLUMNS)
    _write_header(pilots, PILOT_COLUMNS)
    _write_header(ground_truth, GROUND_TRUTH_COLUMNS)
    _append_row(
        interviews,
        INTERVIEW_COLUMNS,
        {
            "interview_id": "I-01",
            "organization_id": "ORG-01",
            "interview_date": "2026-06-11",
            "segment": "developer_ipp",
            "role": "development_director",
            "completed": "true",
            "grid_risk_top_three": "false",
            "late_grid_information_loss": "false",
            "portfolio_shared": "false",
            "pilot_interest": "false",
            "paid_pilot_interest": "false",
            "budget_exists": "false",
            "existing_tools_sufficient": "true",
            "private_information_dependency": "false",
            "decision_comparison_consent": "false",
            "sites_reviewed_per_pursued_site": "1",
            "pre_grid_information_spend_eur": "0",
            "buyer_role": "development_director",
            "budget_owner": "none",
            "use_case": "screening",
            "notes": "",
        },
    )
    _append_row(
        pilots,
        PILOT_COLUMNS,
        {
            "pilot_id": "P-01",
            "organization_id": "ORG-01",
            "portfolio_site_count": "20",
            "agreement_signed": "true",
            "anonymized_metrics_allowed": "true",
            "policy_version": "portfolio-geospatial-v1",
            "sources_frozen": "true",
            "client_prior_ranking_received": "true",
            "delivery_working_days": "3",
            "billed_eur": "0",
            "collected_eur": "0",
            "human_hours": "1",
            "labor_cost_eur_per_hour": "100",
            "other_cost_eur": "0",
            "identity_corrections": "0",
            "recommendation_count": "20",
            "understandable_recommendations": "20",
            "changed_priority_sites": "0",
            "deep_dive_sites": "0",
            "reuse_requested": "false",
            "decisions_recorded_30d": "true",
            "notes": "",
        },
    )
    _append_row(
        ground_truth,
        GROUND_TRUTH_COLUMNS,
        {
            "record_id": "G-001",
            "pilot_id": "P-01",
            "client_site_id": "SITE-001",
            "screening_policy_version": "portfolio-geospatial-v1",
            "screening_class": "A",
            "screening_recommendation": "prioritize",
            "region": "Occitanie",
            "voltage_kv": "225",
            "professionally_reviewed": "false",
            "deep_evidence_type": "none",
            "deep_evidence_outcome": "pending",
            "actual_decision": "pending",
            "abandonment_reason": "",
            "outcome_date": "2026-06-11",
            "notes": "",
        },
    )

    result = run_commercial_validation(
        interviews_path=interviews,
        pilots_path=pilots,
        ground_truth_path=ground_truth,
        output_dir=output,
    )

    for metrics_path, metric_name in (
        (result.interview_metrics_path, "portfolios_shared"),
        (result.pilot_metrics_path, "paid_pilot_count"),
        (result.calibration_metrics_path, "professionally_reviewed_sites"),
    ):
        with metrics_path.open(newline="", encoding="utf-8") as handle:
            by_metric = {
                row["metric"]: row for row in csv.DictReader(handle)
            }
        assert by_metric[metric_name]["status"] == "fail"

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert [source["row_count"] for source in manifest["input_manifests"]] == [1, 1, 1]
