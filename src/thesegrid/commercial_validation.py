from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal


CommercialDecision = Literal[
    "go",
    "reposition",
    "no-go",
    "insufficient_evidence",
]

INTERVIEW_SEGMENTS = {
    "developer_ipp",
    "grid_connection",
    "investor",
    "consultant",
    "aggregator_optimizer",
}
SCREENING_CLASSES = {"A", "B", "C", "D"}
DEEP_EVIDENCE_TYPES = {
    "none",
    "deep_dive",
    "consultant",
    "exploratory_study",
    "ptf",
    "operator",
}
DEEP_EVIDENCE_OUTCOMES = {
    "viable",
    "conditional",
    "not_viable",
    "inconclusive",
    "pending",
}
ACTUAL_DECISIONS = {"promoted", "held", "rejected", "resized", "moved", "pending"}

INTERVIEW_COLUMNS = (
    "interview_id",
    "organization_id",
    "interview_date",
    "segment",
    "role",
    "completed",
    "grid_risk_top_three",
    "late_grid_information_loss",
    "portfolio_shared",
    "pilot_interest",
    "paid_pilot_interest",
    "budget_exists",
    "existing_tools_sufficient",
    "private_information_dependency",
    "decision_comparison_consent",
    "sites_reviewed_per_pursued_site",
    "pre_grid_information_spend_eur",
    "buyer_role",
    "budget_owner",
    "use_case",
    "notes",
)

PILOT_COLUMNS = (
    "pilot_id",
    "organization_id",
    "portfolio_site_count",
    "agreement_signed",
    "anonymized_metrics_allowed",
    "policy_version",
    "sources_frozen",
    "client_prior_ranking_received",
    "delivery_working_days",
    "billed_eur",
    "collected_eur",
    "human_hours",
    "labor_cost_eur_per_hour",
    "other_cost_eur",
    "identity_corrections",
    "recommendation_count",
    "understandable_recommendations",
    "changed_priority_sites",
    "deep_dive_sites",
    "reuse_requested",
    "decisions_recorded_30d",
    "notes",
)

GROUND_TRUTH_COLUMNS = (
    "record_id",
    "pilot_id",
    "client_site_id",
    "screening_policy_version",
    "screening_class",
    "screening_recommendation",
    "region",
    "voltage_kv",
    "professionally_reviewed",
    "deep_evidence_type",
    "deep_evidence_outcome",
    "actual_decision",
    "abandonment_reason",
    "outcome_date",
    "notes",
)


class CommercialValidationError(ValueError):
    pass


@dataclass(frozen=True)
class InterviewRecord:
    interview_id: str
    organization_id: str
    interview_date: str
    segment: str
    role: str
    completed: bool
    grid_risk_top_three: bool | None
    late_grid_information_loss: bool | None
    portfolio_shared: bool | None
    pilot_interest: bool | None
    paid_pilot_interest: bool | None
    budget_exists: bool | None
    existing_tools_sufficient: bool | None
    private_information_dependency: bool | None
    decision_comparison_consent: bool | None
    sites_reviewed_per_pursued_site: float | None
    pre_grid_information_spend_eur: float | None
    buyer_role: str
    budget_owner: str
    use_case: str
    notes: str


@dataclass(frozen=True)
class InterviewMetrics:
    interview_count: int
    completed_interview_count: int
    organization_count: int
    segment_counts: dict[str, int]
    grid_risk_top_three_count: int
    grid_risk_top_three_rate: float | None
    late_grid_information_loss_count: int
    late_grid_information_loss_rate: float | None
    portfolio_shared_count: int
    pilot_interest_count: int
    paid_pilot_interest_count: int
    budget_exists_count: int
    existing_tools_sufficient_count: int
    private_information_dependency_count: int
    decision_comparison_consent_count: int
    go_criteria_met: bool
    decision: CommercialDecision


@dataclass(frozen=True)
class PilotRecord:
    pilot_id: str
    organization_id: str
    portfolio_site_count: int
    agreement_signed: bool
    anonymized_metrics_allowed: bool
    policy_version: str
    sources_frozen: bool
    client_prior_ranking_received: bool
    delivery_working_days: float
    billed_eur: float
    collected_eur: float
    human_hours: float
    labor_cost_eur_per_hour: float
    other_cost_eur: float
    identity_corrections: int
    recommendation_count: int
    understandable_recommendations: int
    changed_priority_sites: int
    deep_dive_sites: int
    reuse_requested: bool
    decisions_recorded_30d: bool
    notes: str

    @property
    def gross_margin_eur(self) -> float:
        return (
            self.billed_eur
            - self.human_hours * self.labor_cost_eur_per_hour
            - self.other_cost_eur
        )


@dataclass(frozen=True)
class PilotMetrics:
    pilot_count: int
    organization_count: int
    total_site_count: int
    paid_pilot_count: int
    collected_pilot_count: int
    signed_agreement_count: int
    anonymized_metrics_allowed_count: int
    frozen_source_count: int
    prior_ranking_count: int
    delivered_within_two_days_count: int
    identity_correction_rate: float | None
    understandable_recommendation_rate: float | None
    changed_priority_rate: float | None
    pilots_with_deep_dive_count: int
    reuse_requested_count: int
    decisions_recorded_30d_count: int
    total_billed_eur: float
    total_collected_eur: float
    total_gross_margin_eur: float
    success_criteria_met: bool
    decision: Literal["validated", "needs_improvement", "insufficient_evidence"]


@dataclass(frozen=True)
class GroundTruthRecord:
    record_id: str
    pilot_id: str
    client_site_id: str
    screening_policy_version: str
    screening_class: str
    screening_recommendation: str
    region: str
    voltage_kv: float
    professionally_reviewed: bool
    deep_evidence_type: str
    deep_evidence_outcome: str
    actual_decision: str
    abandonment_reason: str
    outcome_date: str
    notes: str


@dataclass(frozen=True)
class GroundTruthMetrics:
    site_count: int
    professionally_reviewed_site_count: int
    deep_evidence_site_count: int
    external_evidence_site_count: int
    region_count: int
    voltage_level_count: int
    true_positive_count: int
    true_negative_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float | None
    recall: float | None
    false_positive_rate: float | None
    false_negative_rate: float | None
    calibration_ready: bool


def load_interview_records(path: Path) -> tuple[InterviewRecord, ...]:
    rows = _read_rows(path, INTERVIEW_COLUMNS)
    seen: set[str] = set()
    records: list[InterviewRecord] = []
    for row_number, row in rows:
        interview_id = _required(row, "interview_id", path, row_number)
        if interview_id in seen:
            raise CommercialValidationError(
                f"{path} row {row_number}: duplicate interview_id {interview_id}"
            )
        seen.add(interview_id)
        segment = _required(row, "segment", path, row_number)
        if segment not in INTERVIEW_SEGMENTS:
            raise CommercialValidationError(
                f"{path} row {row_number}: invalid segment {segment}"
            )
        completed = _boolean(row, "completed", path, row_number)
        response_fields = (
            "grid_risk_top_three",
            "late_grid_information_loss",
            "portfolio_shared",
            "pilot_interest",
            "paid_pilot_interest",
            "budget_exists",
            "existing_tools_sufficient",
            "private_information_dependency",
            "decision_comparison_consent",
        )
        responses = {
            field: _optional_boolean(row, field, path, row_number)
            for field in response_fields
        }
        if completed:
            missing = [field for field, value in responses.items() if value is None]
            if missing:
                raise CommercialValidationError(
                    f"{path} row {row_number}: completed interview missing "
                    + ", ".join(missing)
                )
        interview_date = _required(row, "interview_date", path, row_number)
        _iso_date(interview_date, path, row_number, "interview_date")
        records.append(
            InterviewRecord(
                interview_id=interview_id,
                organization_id=_required(
                    row, "organization_id", path, row_number
                ),
                interview_date=interview_date,
                segment=segment,
                role=_required(row, "role", path, row_number),
                completed=completed,
                sites_reviewed_per_pursued_site=_optional_non_negative_float(
                    row,
                    "sites_reviewed_per_pursued_site",
                    path,
                    row_number,
                ),
                pre_grid_information_spend_eur=_optional_non_negative_float(
                    row,
                    "pre_grid_information_spend_eur",
                    path,
                    row_number,
                ),
                buyer_role=str(row["buyer_role"]).strip(),
                budget_owner=str(row["budget_owner"]).strip(),
                use_case=str(row["use_case"]).strip(),
                notes=str(row["notes"]).strip(),
                **responses,
            )
        )
    return tuple(records)


def evaluate_interviews(records: tuple[InterviewRecord, ...]) -> InterviewMetrics:
    completed = tuple(record for record in records if record.completed)
    count = len(completed)
    grid_count = _true_count(completed, "grid_risk_top_three")
    loss_count = _true_count(completed, "late_grid_information_loss")
    shared_count = _true_count(completed, "portfolio_shared")
    pilot_count = _true_count(completed, "pilot_interest")
    paid_count = _true_count(completed, "paid_pilot_interest")
    budget_count = _true_count(completed, "budget_exists")
    sufficient_count = _true_count(completed, "existing_tools_sufficient")
    private_count = _true_count(completed, "private_information_dependency")
    consent_count = _true_count(completed, "decision_comparison_consent")
    grid_rate = _ratio(grid_count, count)
    loss_rate = _ratio(loss_count, count)
    criteria_met = (
        count >= 12
        and grid_rate is not None
        and grid_rate >= 0.70
        and loss_rate is not None
        and loss_rate >= 0.50
        and shared_count >= 5
        and pilot_count >= 3
        and paid_count >= 2
    )
    if criteria_met:
        decision: CommercialDecision = "go"
    elif count < 12:
        decision = "insufficient_evidence"
    elif (
        budget_count == 0
        or sufficient_count == count
        or private_count == count
        or consent_count == 0
    ):
        decision = "no-go"
    else:
        decision = "reposition"
    return InterviewMetrics(
        interview_count=len(records),
        completed_interview_count=count,
        organization_count=len({record.organization_id for record in completed}),
        segment_counts=dict(Counter(record.segment for record in completed)),
        grid_risk_top_three_count=grid_count,
        grid_risk_top_three_rate=grid_rate,
        late_grid_information_loss_count=loss_count,
        late_grid_information_loss_rate=loss_rate,
        portfolio_shared_count=shared_count,
        pilot_interest_count=pilot_count,
        paid_pilot_interest_count=paid_count,
        budget_exists_count=budget_count,
        existing_tools_sufficient_count=sufficient_count,
        private_information_dependency_count=private_count,
        decision_comparison_consent_count=consent_count,
        go_criteria_met=criteria_met,
        decision=decision,
    )


def load_pilot_records(path: Path) -> tuple[PilotRecord, ...]:
    rows = _read_rows(path, PILOT_COLUMNS)
    seen: set[str] = set()
    records: list[PilotRecord] = []
    for row_number, row in rows:
        pilot_id = _required(row, "pilot_id", path, row_number)
        if pilot_id in seen:
            raise CommercialValidationError(
                f"{path} row {row_number}: duplicate pilot_id {pilot_id}"
            )
        seen.add(pilot_id)
        site_count = _integer(row, "portfolio_site_count", path, row_number)
        if not 20 <= site_count <= 100:
            raise CommercialValidationError(
                f"{path} row {row_number}: portfolio_site_count must be between 20 and 100"
            )
        recommendation_count = _integer(
            row, "recommendation_count", path, row_number
        )
        corrections = _integer(row, "identity_corrections", path, row_number)
        understandable = _integer(
            row, "understandable_recommendations", path, row_number
        )
        changed = _integer(row, "changed_priority_sites", path, row_number)
        deep_dive = _integer(row, "deep_dive_sites", path, row_number)
        billed_eur = _non_negative_float(
            row, "billed_eur", path, row_number
        )
        collected_eur = _non_negative_float(
            row, "collected_eur", path, row_number
        )
        if collected_eur > billed_eur:
            raise CommercialValidationError(
                f"{path} row {row_number}: collected_eur cannot exceed billed_eur"
            )
        for field, value, maximum in (
            ("identity_corrections", corrections, site_count),
            ("recommendation_count", recommendation_count, site_count),
            ("understandable_recommendations", understandable, recommendation_count),
            ("changed_priority_sites", changed, site_count),
            ("deep_dive_sites", deep_dive, site_count),
        ):
            if value < 0 or value > maximum:
                raise CommercialValidationError(
                    f"{path} row {row_number}: {field} must be between 0 and {maximum}"
                )
        records.append(
            PilotRecord(
                pilot_id=pilot_id,
                organization_id=_required(
                    row, "organization_id", path, row_number
                ),
                portfolio_site_count=site_count,
                agreement_signed=_boolean(
                    row, "agreement_signed", path, row_number
                ),
                anonymized_metrics_allowed=_boolean(
                    row, "anonymized_metrics_allowed", path, row_number
                ),
                policy_version=_required(
                    row, "policy_version", path, row_number
                ),
                sources_frozen=_boolean(
                    row, "sources_frozen", path, row_number
                ),
                client_prior_ranking_received=_boolean(
                    row,
                    "client_prior_ranking_received",
                    path,
                    row_number,
                ),
                delivery_working_days=_non_negative_float(
                    row, "delivery_working_days", path, row_number
                ),
                billed_eur=billed_eur,
                collected_eur=collected_eur,
                human_hours=_non_negative_float(
                    row, "human_hours", path, row_number
                ),
                labor_cost_eur_per_hour=_non_negative_float(
                    row, "labor_cost_eur_per_hour", path, row_number
                ),
                other_cost_eur=_non_negative_float(
                    row, "other_cost_eur", path, row_number
                ),
                identity_corrections=corrections,
                recommendation_count=recommendation_count,
                understandable_recommendations=understandable,
                changed_priority_sites=changed,
                deep_dive_sites=deep_dive,
                reuse_requested=_boolean(
                    row, "reuse_requested", path, row_number
                ),
                decisions_recorded_30d=_boolean(
                    row, "decisions_recorded_30d", path, row_number
                ),
                notes=str(row["notes"]).strip(),
            )
        )
    return tuple(records)


def evaluate_pilots(records: tuple[PilotRecord, ...]) -> PilotMetrics:
    sites = sum(record.portfolio_site_count for record in records)
    recommendations = sum(record.recommendation_count for record in records)
    correction_rate = _ratio(
        sum(record.identity_corrections for record in records), sites
    )
    understandable_rate = _ratio(
        sum(record.understandable_recommendations for record in records),
        recommendations,
    )
    changed_rate = _ratio(
        sum(record.changed_priority_sites for record in records), sites
    )
    paid_count = sum(record.billed_eur > 0 for record in records)
    deep_count = sum(record.deep_dive_sites > 0 for record in records)
    reuse_count = sum(record.reuse_requested for record in records)
    total_margin = sum(record.gross_margin_eur for record in records)
    criteria_met = (
        len(records) >= 3
        and paid_count >= 2
        and all(record.agreement_signed for record in records)
        and all(record.anonymized_metrics_allowed for record in records)
        and all(record.sources_frozen for record in records)
        and all(record.client_prior_ranking_received for record in records)
        and all(record.decisions_recorded_30d for record in records)
        and all(record.delivery_working_days < 2 for record in records)
        and correction_rate is not None
        and correction_rate < 0.10
        and understandable_rate is not None
        and understandable_rate >= 0.80
        and changed_rate is not None
        and changed_rate >= 0.30
        and deep_count == len(records)
        and reuse_count >= 2
        and total_margin > 0
    )
    decision: Literal["validated", "needs_improvement", "insufficient_evidence"]
    if criteria_met:
        decision = "validated"
    elif len(records) < 3:
        decision = "insufficient_evidence"
    else:
        decision = "needs_improvement"
    return PilotMetrics(
        pilot_count=len(records),
        organization_count=len({record.organization_id for record in records}),
        total_site_count=sites,
        paid_pilot_count=paid_count,
        collected_pilot_count=sum(record.collected_eur > 0 for record in records),
        signed_agreement_count=sum(record.agreement_signed for record in records),
        anonymized_metrics_allowed_count=sum(
            record.anonymized_metrics_allowed for record in records
        ),
        frozen_source_count=sum(record.sources_frozen for record in records),
        prior_ranking_count=sum(
            record.client_prior_ranking_received for record in records
        ),
        delivered_within_two_days_count=sum(
            record.delivery_working_days < 2 for record in records
        ),
        identity_correction_rate=correction_rate,
        understandable_recommendation_rate=understandable_rate,
        changed_priority_rate=changed_rate,
        pilots_with_deep_dive_count=deep_count,
        reuse_requested_count=reuse_count,
        decisions_recorded_30d_count=sum(
            record.decisions_recorded_30d for record in records
        ),
        total_billed_eur=round(sum(record.billed_eur for record in records), 2),
        total_collected_eur=round(
            sum(record.collected_eur for record in records), 2
        ),
        total_gross_margin_eur=round(total_margin, 2),
        success_criteria_met=criteria_met,
        decision=decision,
    )


def load_ground_truth_records(path: Path) -> tuple[GroundTruthRecord, ...]:
    rows = _read_rows(path, GROUND_TRUTH_COLUMNS)
    seen_records: set[str] = set()
    seen_sites: set[tuple[str, str]] = set()
    records: list[GroundTruthRecord] = []
    for row_number, row in rows:
        record_id = _required(row, "record_id", path, row_number)
        if record_id in seen_records:
            raise CommercialValidationError(
                f"{path} row {row_number}: duplicate record_id {record_id}"
            )
        seen_records.add(record_id)
        pilot_id = _required(row, "pilot_id", path, row_number)
        site_id = _required(row, "client_site_id", path, row_number)
        site_key = (pilot_id, site_id)
        if site_key in seen_sites:
            raise CommercialValidationError(
                f"{path} row {row_number}: duplicate pilot/site {pilot_id}/{site_id}"
            )
        seen_sites.add(site_key)
        screening_class = _required(
            row, "screening_class", path, row_number
        ).upper()
        if screening_class not in SCREENING_CLASSES:
            raise CommercialValidationError(
                f"{path} row {row_number}: invalid screening_class {screening_class}"
            )
        evidence_type = _enum(
            row,
            "deep_evidence_type",
            DEEP_EVIDENCE_TYPES,
            path,
            row_number,
        )
        evidence_outcome = _enum(
            row,
            "deep_evidence_outcome",
            DEEP_EVIDENCE_OUTCOMES,
            path,
            row_number,
        )
        if evidence_type == "none" and evidence_outcome not in {
            "inconclusive",
            "pending",
        }:
            raise CommercialValidationError(
                f"{path} row {row_number}: deep_evidence_outcome "
                f"{evidence_outcome} requires a deep_evidence_type"
            )
        actual_decision = _enum(
            row, "actual_decision", ACTUAL_DECISIONS, path, row_number
        )
        outcome_date = _required(row, "outcome_date", path, row_number)
        _iso_date(outcome_date, path, row_number, "outcome_date")
        records.append(
            GroundTruthRecord(
                record_id=record_id,
                pilot_id=pilot_id,
                client_site_id=site_id,
                screening_policy_version=_required(
                    row, "screening_policy_version", path, row_number
                ),
                screening_class=screening_class,
                screening_recommendation=_required(
                    row, "screening_recommendation", path, row_number
                ),
                region=_required(row, "region", path, row_number),
                voltage_kv=_positive_float(
                    row, "voltage_kv", path, row_number
                ),
                professionally_reviewed=_boolean(
                    row, "professionally_reviewed", path, row_number
                ),
                deep_evidence_type=evidence_type,
                deep_evidence_outcome=evidence_outcome,
                actual_decision=actual_decision,
                abandonment_reason=str(row["abandonment_reason"]).strip(),
                outcome_date=outcome_date,
                notes=str(row["notes"]).strip(),
            )
        )
    return tuple(records)


def evaluate_ground_truth(
    records: tuple[GroundTruthRecord, ...],
) -> GroundTruthMetrics:
    deep_records = tuple(
        record for record in records if record.deep_evidence_type != "none"
    )
    external_records = tuple(
        record
        for record in records
        if record.deep_evidence_type
        in {"consultant", "exploratory_study", "ptf", "operator"}
    )
    tp = tn = fp = fn = 0
    for record in records:
        if record.deep_evidence_outcome not in {
            "viable",
            "conditional",
            "not_viable",
        }:
            continue
        predicted_positive = record.screening_class in {"A", "B"}
        actual_positive = record.deep_evidence_outcome in {"viable", "conditional"}
        if predicted_positive and actual_positive:
            tp += 1
        elif predicted_positive:
            fp += 1
        elif actual_positive:
            fn += 1
        else:
            tn += 1
    reviewed = sum(record.professionally_reviewed for record in records)
    regions = {record.region.upper() for record in records if record.region}
    voltages = {round(record.voltage_kv, 6) for record in records}
    return GroundTruthMetrics(
        site_count=len(records),
        professionally_reviewed_site_count=reviewed,
        deep_evidence_site_count=len(deep_records),
        external_evidence_site_count=len(external_records),
        region_count=len(regions),
        voltage_level_count=len(voltages),
        true_positive_count=tp,
        true_negative_count=tn,
        false_positive_count=fp,
        false_negative_count=fn,
        precision=_ratio(tp, tp + fp),
        recall=_ratio(tp, tp + fn),
        false_positive_rate=_ratio(fp, fp + tn),
        false_negative_rate=_ratio(fn, fn + tp),
        calibration_ready=(
            reviewed >= 50
            and len(deep_records) >= 15
            and len(regions) >= 2
            and len(voltages) >= 2
        ),
    )


def _read_rows(
    path: Path,
    required_columns: tuple[str, ...],
) -> tuple[tuple[int, dict[str, str]], ...]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = [
                column
                for column in required_columns
                if column not in (reader.fieldnames or ())
            ]
            if missing:
                raise CommercialValidationError(
                    f"{path} missing required columns: {', '.join(missing)}"
                )
            return tuple(
                (row_number, {key: value or "" for key, value in row.items()})
                for row_number, row in enumerate(reader, start=2)
            )
    except OSError as exc:
        raise CommercialValidationError(f"cannot read {path}: {exc}") from exc


def _required(
    row: dict[str, str],
    field: str,
    path: Path,
    row_number: int,
) -> str:
    value = str(row[field]).strip()
    if not value:
        raise CommercialValidationError(
            f"{path} row {row_number}: {field} is required"
        )
    return value


def _boolean(
    row: dict[str, str],
    field: str,
    path: Path,
    row_number: int,
) -> bool:
    value = _optional_boolean(row, field, path, row_number)
    if value is None:
        raise CommercialValidationError(
            f"{path} row {row_number}: {field} is required"
        )
    return value


def _optional_boolean(
    row: dict[str, str],
    field: str,
    path: Path,
    row_number: int,
) -> bool | None:
    value = str(row[field]).strip().lower()
    if not value:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    raise CommercialValidationError(
        f"{path} row {row_number}: {field} must be true or false"
    )


def _integer(
    row: dict[str, str],
    field: str,
    path: Path,
    row_number: int,
) -> int:
    value = _non_negative_float(row, field, path, row_number)
    if not value.is_integer():
        raise CommercialValidationError(
            f"{path} row {row_number}: {field} must be an integer"
        )
    return int(value)


def _positive_float(
    row: dict[str, str],
    field: str,
    path: Path,
    row_number: int,
) -> float:
    value = _non_negative_float(row, field, path, row_number)
    if value <= 0:
        raise CommercialValidationError(
            f"{path} row {row_number}: {field} must be positive"
        )
    return value


def _non_negative_float(
    row: dict[str, str],
    field: str,
    path: Path,
    row_number: int,
) -> float:
    value = _number(str(row[field]).strip(), field, path, row_number)
    if value < 0:
        raise CommercialValidationError(
            f"{path} row {row_number}: {field} must be non-negative"
        )
    return value


def _optional_non_negative_float(
    row: dict[str, str],
    field: str,
    path: Path,
    row_number: int,
) -> float | None:
    text = str(row[field]).strip()
    if not text:
        return None
    value = _number(text, field, path, row_number)
    if value < 0:
        raise CommercialValidationError(
            f"{path} row {row_number}: {field} must be non-negative"
        )
    return value


def _number(
    value: str,
    field: str,
    path: Path,
    row_number: int,
) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise CommercialValidationError(
            f"{path} row {row_number}: {field} must be a number"
        ) from exc
    if not math.isfinite(parsed):
        raise CommercialValidationError(
            f"{path} row {row_number}: {field} must be finite"
        )
    return parsed


def _enum(
    row: dict[str, str],
    field: str,
    accepted: set[str],
    path: Path,
    row_number: int,
) -> str:
    value = _required(row, field, path, row_number)
    if value not in accepted:
        raise CommercialValidationError(
            f"{path} row {row_number}: invalid {field} {value}"
        )
    return value


def _iso_date(value: str, path: Path, row_number: int, field: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise CommercialValidationError(
            f"{path} row {row_number}: {field} must use YYYY-MM-DD"
        ) from exc


def _true_count(records: tuple[InterviewRecord, ...], field: str) -> int:
    return sum(getattr(record, field) is True for record in records)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
