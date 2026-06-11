from __future__ import annotations

import csv
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from thesegrid.commercial_validation import (
    GroundTruthMetrics,
    InterviewMetrics,
    PilotMetrics,
    evaluate_ground_truth,
    evaluate_interviews,
    evaluate_pilots,
    load_ground_truth_records,
    load_interview_records,
    load_pilot_records,
)
from thesegrid.public_data.sources import local_source_manifest


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CommercialValidationOutputs:
    summary_path: Path
    report_path: Path
    interview_metrics_path: Path
    pilot_metrics_path: Path
    calibration_metrics_path: Path
    manifest_path: Path


def run_commercial_validation(
    *,
    interviews_path: Path,
    pilots_path: Path,
    ground_truth_path: Path,
    output_dir: Path,
    now: Clock | None = None,
) -> CommercialValidationOutputs:
    interviews = evaluate_interviews(load_interview_records(interviews_path))
    pilots = evaluate_pilots(load_pilot_records(pilots_path))
    ground_truth = evaluate_ground_truth(
        load_ground_truth_records(ground_truth_path)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = CommercialValidationOutputs(
        summary_path=output_dir / "commercial_validation_summary.json",
        report_path=output_dir / "commercial_validation_report.md",
        interview_metrics_path=output_dir / "interview_metrics.csv",
        pilot_metrics_path=output_dir / "pilot_metrics.csv",
        calibration_metrics_path=output_dir / "calibration_metrics.csv",
        manifest_path=output_dir / "commercial_validation_manifest.json",
    )
    interview_rows = _interview_metric_rows(interviews)
    pilot_rows = _pilot_metric_rows(pilots)
    calibration_rows = _calibration_metric_rows(ground_truth)
    _write_metric_rows(outputs.interview_metrics_path, interview_rows)
    _write_metric_rows(outputs.pilot_metrics_path, pilot_rows)
    _write_metric_rows(outputs.calibration_metrics_path, calibration_rows)

    overall_decision = _overall_decision(interviews, pilots, ground_truth)
    remaining_actions = _remaining_external_actions(
        interviews, pilots, ground_truth
    )
    summary = {
        "product": "VoltPath Commercial Validation",
        "overall_decision": overall_decision,
        "interviews": asdict(interviews),
        "pilots": asdict(pilots),
        "ground_truth": asdict(ground_truth),
        "remaining_external_actions": remaining_actions,
        "evidence_boundary": (
            "No customer, payment, or grid-study outcome is inferred from missing data."
        ),
    }
    outputs.summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    outputs.report_path.write_text(
        _render_report(
            overall_decision,
            interviews,
            pilots,
            ground_truth,
            interview_rows,
            pilot_rows,
            calibration_rows,
            remaining_actions,
        ),
        encoding="utf-8",
    )

    created_at = _as_utc((now or _utc_now)())
    manifests = (
        local_source_manifest(
            interviews_path,
            "commercial_interviews",
            row_count=interviews.interview_count,
            quality={"completed_interviews": interviews.completed_interview_count},
            now=lambda: created_at,
        ),
        local_source_manifest(
            pilots_path,
            "commercial_pilots",
            row_count=pilots.pilot_count,
            quality={"paid_pilots": pilots.paid_pilot_count},
            now=lambda: created_at,
        ),
        local_source_manifest(
            ground_truth_path,
            "commercial_ground_truth",
            row_count=ground_truth.site_count,
            quality={
                "professionally_reviewed_sites": (
                    ground_truth.professionally_reviewed_site_count
                ),
                "deep_evidence_sites": ground_truth.deep_evidence_site_count,
            },
            now=lambda: created_at,
        ),
    )
    manifest = {
        "product": "VoltPath Commercial Validation",
        "created_at_utc": created_at.isoformat(),
        "input_manifests": [_json_value(asdict(item)) for item in manifests],
        "outputs": {
            "summary": outputs.summary_path.name,
            "report": outputs.report_path.name,
            "interview_metrics": outputs.interview_metrics_path.name,
            "pilot_metrics": outputs.pilot_metrics_path.name,
            "calibration_metrics": outputs.calibration_metrics_path.name,
        },
    }
    outputs.manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return outputs


def _overall_decision(
    interviews: InterviewMetrics,
    pilots: PilotMetrics,
    ground_truth: GroundTruthMetrics,
) -> str:
    if (
        interviews.go_criteria_met
        and pilots.success_criteria_met
        and ground_truth.calibration_ready
    ):
        return "validated_for_next_stage"
    if (
        interviews.completed_interview_count == 0
        and pilots.pilot_count == 0
        and ground_truth.site_count == 0
    ):
        return "insufficient_evidence"
    if interviews.decision == "no-go":
        return "no-go"
    return "go-with-conditions"


def _remaining_external_actions(
    interviews: InterviewMetrics,
    pilots: PilotMetrics,
    ground_truth: GroundTruthMetrics,
) -> list[str]:
    actions: list[str] = []
    if interviews.completed_interview_count < 12:
        actions.append(
            f"Complete {12 - interviews.completed_interview_count} additional interviews."
        )
    if interviews.portfolio_shared_count < 5:
        actions.append(
            f"Obtain {5 - interviews.portfolio_shared_count} additional anonymized portfolios."
        )
    if pilots.pilot_count < 3:
        actions.append(f"Run {3 - pilots.pilot_count} additional Portfolio Screening pilots.")
    if pilots.paid_pilot_count < 2:
        actions.append(f"Invoice {2 - pilots.paid_pilot_count} additional paid pilots.")
    if ground_truth.professionally_reviewed_site_count < 50:
        actions.append(
            "Professionally review "
            f"{50 - ground_truth.professionally_reviewed_site_count} additional sites."
        )
    if ground_truth.deep_evidence_site_count < 15:
        actions.append(
            "Collect deeper evidence for "
            f"{15 - ground_truth.deep_evidence_site_count} additional sites."
        )
    if ground_truth.region_count < 2:
        actions.append("Add outcomes from at least two French regions.")
    if ground_truth.voltage_level_count < 2:
        actions.append("Add outcomes from at least two connection voltage levels.")
    return actions


def _interview_metric_rows(metrics: InterviewMetrics) -> list[dict[str, object]]:
    measured = metrics.completed_interview_count > 0
    return [
        _metric(
            "completed_interviews",
            metrics.completed_interview_count,
            ">= 12",
            12,
            measured=measured,
        ),
        _metric(
            "developer_ipp_interviews",
            metrics.segment_counts.get("developer_ipp", 0),
            ">= 8",
            8,
            measured=measured,
        ),
        _metric(
            "grid_connection_interviews",
            metrics.segment_counts.get("grid_connection", 0),
            ">= 3",
            3,
            measured=measured,
        ),
        _metric(
            "investor_interviews",
            metrics.segment_counts.get("investor", 0),
            ">= 3",
            3,
            measured=measured,
        ),
        _metric(
            "consultant_interviews",
            metrics.segment_counts.get("consultant", 0),
            ">= 3",
            3,
            measured=measured,
        ),
        _metric(
            "aggregator_optimizer_interviews",
            metrics.segment_counts.get("aggregator_optimizer", 0),
            ">= 2",
            2,
            measured=measured,
        ),
        _rate_metric(
            "grid_risk_top_three_rate",
            metrics.grid_risk_top_three_rate,
            ">= 70%",
            0.70,
        ),
        _rate_metric(
            "late_grid_information_loss_rate",
            metrics.late_grid_information_loss_rate,
            ">= 50%",
            0.50,
        ),
        _metric(
            "portfolios_shared",
            metrics.portfolio_shared_count,
            ">= 5",
            5,
            measured=measured,
        ),
        _metric(
            "pilot_interest",
            metrics.pilot_interest_count,
            ">= 3",
            3,
            measured=measured,
        ),
        _metric(
            "paid_pilot_interest",
            metrics.paid_pilot_interest_count,
            ">= 2",
            2,
            measured=measured,
        ),
    ]


def _pilot_metric_rows(metrics: PilotMetrics) -> list[dict[str, object]]:
    measured = metrics.pilot_count > 0
    return [
        _metric(
            "pilot_count",
            metrics.pilot_count,
            ">= 3",
            3,
            measured=measured,
        ),
        _metric(
            "paid_pilot_count",
            metrics.paid_pilot_count,
            ">= 2",
            2,
            measured=measured,
        ),
        _metric(
            "signed_agreements",
            metrics.signed_agreement_count,
            "one per pilot",
            metrics.pilot_count,
            measured=measured,
        ),
        _metric(
            "anonymized_metrics_allowed",
            metrics.anonymized_metrics_allowed_count,
            "one per pilot",
            metrics.pilot_count,
            measured=measured,
        ),
        _metric(
            "decisions_recorded_30d",
            metrics.decisions_recorded_30d_count,
            "one per pilot",
            metrics.pilot_count,
            measured=measured,
        ),
        _rate_metric(
            "identity_correction_rate",
            metrics.identity_correction_rate,
            "< 10%",
            0.10,
            maximum=True,
        ),
        _rate_metric(
            "understandable_recommendation_rate",
            metrics.understandable_recommendation_rate,
            ">= 80%",
            0.80,
        ),
        _rate_metric(
            "changed_priority_rate",
            metrics.changed_priority_rate,
            ">= 30%",
            0.30,
        ),
        _metric(
            "pilots_with_deep_dive",
            metrics.pilots_with_deep_dive_count,
            "one per pilot",
            metrics.pilot_count,
            measured=measured,
        ),
        _metric(
            "reuse_requested",
            metrics.reuse_requested_count,
            ">= 2",
            2,
            measured=measured,
        ),
        {
            "metric": "total_gross_margin_eur",
            "measured_value": metrics.total_gross_margin_eur,
            "threshold": "> 0",
            "status": (
                "not_measured"
                if metrics.pilot_count == 0
                else ("pass" if metrics.total_gross_margin_eur > 0 else "fail")
            ),
        },
    ]


def _calibration_metric_rows(
    metrics: GroundTruthMetrics,
) -> list[dict[str, object]]:
    measured = metrics.site_count > 0
    return [
        _metric(
            "professionally_reviewed_sites",
            metrics.professionally_reviewed_site_count,
            ">= 50",
            50,
            measured=measured,
        ),
        _metric(
            "deep_evidence_sites",
            metrics.deep_evidence_site_count,
            ">= 15",
            15,
            measured=measured,
        ),
        _metric(
            "represented_regions",
            metrics.region_count,
            ">= 2",
            2,
            measured=measured,
        ),
        _metric(
            "represented_voltage_levels",
            metrics.voltage_level_count,
            ">= 2",
            2,
            measured=measured,
        ),
        {
            "metric": "precision",
            "measured_value": _format_optional_rate(metrics.precision),
            "threshold": "calibrate",
            "status": "not_measured" if metrics.precision is None else "measured",
        },
        {
            "metric": "recall",
            "measured_value": _format_optional_rate(metrics.recall),
            "threshold": "calibrate",
            "status": "not_measured" if metrics.recall is None else "measured",
        },
    ]


def _metric(
    name: str,
    value: int,
    threshold_text: str,
    threshold: int,
    *,
    measured: bool,
) -> dict[str, object]:
    return {
        "metric": name,
        "measured_value": value,
        "threshold": threshold_text,
        "status": (
            "not_measured"
            if not measured
            else ("pass" if value >= threshold else "fail")
        ),
    }


def _rate_metric(
    name: str,
    value: float | None,
    threshold_text: str,
    threshold: float,
    *,
    maximum: bool = False,
) -> dict[str, object]:
    passed = False if value is None else (value < threshold if maximum else value >= threshold)
    return {
        "metric": name,
        "measured_value": _format_optional_rate(value),
        "threshold": threshold_text,
        "status": "not_measured" if value is None else ("pass" if passed else "fail"),
    }


def _format_optional_rate(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def _write_metric_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("metric", "measured_value", "threshold", "status"),
        )
        writer.writeheader()
        writer.writerows(rows)


def _render_report(
    overall_decision: str,
    interviews: InterviewMetrics,
    pilots: PilotMetrics,
    ground_truth: GroundTruthMetrics,
    interview_rows: list[dict[str, object]],
    pilot_rows: list[dict[str, object]],
    calibration_rows: list[dict[str, object]],
    remaining_actions: list[str],
) -> str:
    lines = [
        "# VoltPath Commercial Validation",
        "",
        f"**Overall decision:** `{overall_decision}`",
        "",
        (
            "No customer, payment, or grid-study outcome is inferred from missing "
            "evidence."
        ),
        "",
        "## Phase 1 - Interviews",
        "",
        f"Decision: `{interviews.decision}`.",
        "",
        *_metric_table(interview_rows),
        "",
        "## Phase 2 - Portfolio Screening Pilots",
        "",
        f"Decision: `{pilots.decision}`.",
        "",
        *_metric_table(pilot_rows),
        "",
        "## Phase 3 - Ground Truth and Calibration",
        "",
        f"Calibration ready: `{str(ground_truth.calibration_ready).lower()}`.",
        "",
        *_metric_table(calibration_rows),
        "",
        "## Remaining External Actions",
        "",
    ]
    if remaining_actions:
        lines.extend(f"- {action}" for action in remaining_actions)
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Evidence Boundary",
            "",
            (
                "This workflow measures commercial and calibration evidence supplied "
                "to it. It does not create prospects, interviews, invoices, client "
                "decisions, PTF results, or operator validation."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _metric_table(rows: list[dict[str, object]]) -> list[str]:
    lines = [
        "| Metric | Measured | Threshold | Status |",
        "|---|---:|---:|---|",
    ]
    lines.extend(
        f"| {row['metric']} | {row['measured_value']} | {row['threshold']} | {row['status']} |"
        for row in rows
    )
    return lines


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
