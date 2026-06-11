from __future__ import annotations

from pathlib import Path

import pytest

from thesegrid.commercial_validation import (
    CommercialValidationError,
    evaluate_ground_truth,
    evaluate_interviews,
    evaluate_pilots,
    load_ground_truth_records,
    load_interview_records,
    load_pilot_records,
)


INTERVIEW_HEADER = (
    "interview_id,organization_id,interview_date,segment,role,completed,"
    "grid_risk_top_three,late_grid_information_loss,portfolio_shared,pilot_interest,"
    "paid_pilot_interest,budget_exists,existing_tools_sufficient,"
    "private_information_dependency,decision_comparison_consent,"
    "sites_reviewed_per_pursued_site,pre_grid_information_spend_eur,buyer_role,"
    "budget_owner,use_case,notes\n"
)


def _interview_row(index: int, **overrides: object) -> str:
    values: dict[str, object] = {
        "interview_id": f"I-{index:02d}",
        "organization_id": f"ORG-{index:02d}",
        "interview_date": "2026-06-11",
        "segment": "developer_ipp",
        "role": "development_director",
        "completed": "true",
        "grid_risk_top_three": "true",
        "late_grid_information_loss": "true",
        "portfolio_shared": "true",
        "pilot_interest": "true",
        "paid_pilot_interest": "true",
        "budget_exists": "true",
        "existing_tools_sufficient": "false",
        "private_information_dependency": "false",
        "decision_comparison_consent": "true",
        "sites_reviewed_per_pursued_site": "8",
        "pre_grid_information_spend_eur": "25000",
        "buyer_role": "development_director",
        "budget_owner": "technical_direction",
        "use_case": "ptf_prioritization",
        "notes": "Pseudonymized interview.",
    }
    values.update(overrides)
    return ",".join(str(values[column]) for column in INTERVIEW_HEADER.strip().split(",")) + "\n"


def test_interview_evaluation_applies_roadmap_go_thresholds(tmp_path: Path):
    path = tmp_path / "interviews.csv"
    path.write_text(
        INTERVIEW_HEADER
        + "".join(
            _interview_row(
                index,
                portfolio_shared="true" if index <= 5 else "false",
                pilot_interest="true" if index <= 3 else "false",
                paid_pilot_interest="true" if index <= 2 else "false",
            )
            for index in range(1, 13)
        ),
        encoding="utf-8",
    )

    metrics = evaluate_interviews(load_interview_records(path))

    assert metrics.completed_interview_count == 12
    assert metrics.grid_risk_top_three_rate == 1.0
    assert metrics.late_grid_information_loss_rate == 1.0
    assert metrics.portfolio_shared_count == 5
    assert metrics.pilot_interest_count == 3
    assert metrics.paid_pilot_interest_count == 2
    assert metrics.decision == "go"
    assert metrics.go_criteria_met is True


def test_interview_evaluation_never_claims_success_with_too_few_records(tmp_path: Path):
    path = tmp_path / "interviews.csv"
    path.write_text(
        INTERVIEW_HEADER + "".join(_interview_row(index) for index in range(1, 4)),
        encoding="utf-8",
    )

    metrics = evaluate_interviews(load_interview_records(path))

    assert metrics.completed_interview_count == 3
    assert metrics.decision == "insufficient_evidence"
    assert metrics.go_criteria_met is False


def test_interview_evaluation_rejects_exclusive_private_information_dependency(
    tmp_path: Path,
):
    path = tmp_path / "interviews.csv"
    path.write_text(
        INTERVIEW_HEADER
        + "".join(
            _interview_row(
                index,
                private_information_dependency="true",
                portfolio_shared="false",
                pilot_interest="false",
                paid_pilot_interest="false",
            )
            for index in range(1, 13)
        ),
        encoding="utf-8",
    )

    metrics = evaluate_interviews(load_interview_records(path))

    assert metrics.decision == "no-go"


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (_interview_row(1, completed="yes"), "completed"),
        (_interview_row(1, segment="utility"), "segment"),
        (_interview_row(1, pre_grid_information_spend_eur="-1"), "non-negative"),
        (
            _interview_row(1) + _interview_row(1),
            "duplicate interview_id",
        ),
    ],
)
def test_interview_loader_rejects_invalid_contract(
    tmp_path: Path,
    row: str,
    message: str,
):
    path = tmp_path / "interviews.csv"
    path.write_text(INTERVIEW_HEADER + row, encoding="utf-8")

    with pytest.raises(CommercialValidationError, match=message):
        load_interview_records(path)


PILOT_HEADER = (
    "pilot_id,organization_id,portfolio_site_count,agreement_signed,"
    "anonymized_metrics_allowed,policy_version,sources_frozen,"
    "client_prior_ranking_received,delivery_working_days,billed_eur,collected_eur,"
    "human_hours,labor_cost_eur_per_hour,other_cost_eur,identity_corrections,"
    "recommendation_count,understandable_recommendations,changed_priority_sites,"
    "deep_dive_sites,reuse_requested,decisions_recorded_30d,notes\n"
)


def _pilot_row(index: int, **overrides: object) -> str:
    values: dict[str, object] = {
        "pilot_id": f"P-{index:02d}",
        "organization_id": f"ORG-{index:02d}",
        "portfolio_site_count": "50",
        "agreement_signed": "true",
        "anonymized_metrics_allowed": "true",
        "policy_version": "portfolio-geospatial-v1",
        "sources_frozen": "true",
        "client_prior_ranking_received": "true",
        "delivery_working_days": "1.5",
        "billed_eur": "6000",
        "collected_eur": "6000",
        "human_hours": "20",
        "labor_cost_eur_per_hour": "100",
        "other_cost_eur": "500",
        "identity_corrections": "2",
        "recommendation_count": "50",
        "understandable_recommendations": "45",
        "changed_priority_sites": "20",
        "deep_dive_sites": "1",
        "reuse_requested": "true",
        "decisions_recorded_30d": "true",
        "notes": "Pseudonymized pilot.",
    }
    values.update(overrides)
    return ",".join(str(values[column]) for column in PILOT_HEADER.strip().split(",")) + "\n"


def test_pilot_evaluation_measures_delivery_quality_and_margin(tmp_path: Path):
    path = tmp_path / "pilots.csv"
    path.write_text(
        PILOT_HEADER
        + _pilot_row(1)
        + _pilot_row(2)
        + _pilot_row(3, billed_eur="0", collected_eur="0", reuse_requested="false"),
        encoding="utf-8",
    )

    metrics = evaluate_pilots(load_pilot_records(path))

    assert metrics.pilot_count == 3
    assert metrics.paid_pilot_count == 2
    assert metrics.identity_correction_rate == pytest.approx(6 / 150)
    assert metrics.understandable_recommendation_rate == pytest.approx(135 / 150)
    assert metrics.changed_priority_rate == pytest.approx(60 / 150)
    assert metrics.pilots_with_deep_dive_count == 3
    assert metrics.reuse_requested_count == 2
    assert metrics.total_gross_margin_eur == pytest.approx(4_500)
    assert metrics.success_criteria_met is True


def test_pilot_evaluation_reports_insufficient_evidence_before_three_pilots(
    tmp_path: Path,
):
    path = tmp_path / "pilots.csv"
    path.write_text(PILOT_HEADER + _pilot_row(1), encoding="utf-8")

    metrics = evaluate_pilots(load_pilot_records(path))

    assert metrics.decision == "insufficient_evidence"
    assert metrics.success_criteria_met is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"anonymized_metrics_allowed": "false"},
        {"decisions_recorded_30d": "false"},
    ],
)
def test_pilot_evaluation_requires_auditable_follow_up(
    tmp_path: Path,
    overrides: dict[str, str],
):
    path = tmp_path / "pilots.csv"
    path.write_text(
        PILOT_HEADER
        + _pilot_row(1, **overrides)
        + _pilot_row(2)
        + _pilot_row(3, billed_eur="0", collected_eur="0", reuse_requested="false"),
        encoding="utf-8",
    )

    metrics = evaluate_pilots(load_pilot_records(path))

    assert metrics.success_criteria_met is False
    assert metrics.decision == "needs_improvement"


def test_pilot_loader_rejects_inconsistent_counts(tmp_path: Path):
    path = tmp_path / "pilots.csv"
    path.write_text(
        PILOT_HEADER + _pilot_row(1, identity_corrections="51"),
        encoding="utf-8",
    )

    with pytest.raises(CommercialValidationError, match="identity_corrections"):
        load_pilot_records(path)


def test_pilot_loader_rejects_collection_above_billed_amount(tmp_path: Path):
    path = tmp_path / "pilots.csv"
    path.write_text(
        PILOT_HEADER + _pilot_row(1, billed_eur="1000", collected_eur="1001"),
        encoding="utf-8",
    )

    with pytest.raises(CommercialValidationError, match="collected_eur"):
        load_pilot_records(path)


GROUND_TRUTH_HEADER = (
    "record_id,pilot_id,client_site_id,screening_policy_version,screening_class,"
    "screening_recommendation,region,voltage_kv,professionally_reviewed,"
    "deep_evidence_type,deep_evidence_outcome,actual_decision,abandonment_reason,"
    "outcome_date,notes\n"
)


def _ground_truth_row(index: int, **overrides: object) -> str:
    values: dict[str, object] = {
        "record_id": f"G-{index:03d}",
        "pilot_id": "P-01",
        "client_site_id": f"SITE-{index:03d}",
        "screening_policy_version": "portfolio-geospatial-v1",
        "screening_class": "A",
        "screening_recommendation": "prioritize",
        "region": "Occitanie",
        "voltage_kv": "225",
        "professionally_reviewed": "true",
        "deep_evidence_type": "ptf",
        "deep_evidence_outcome": "viable",
        "actual_decision": "promoted",
        "abandonment_reason": "",
        "outcome_date": "2026-06-11",
        "notes": "Pseudonymized site outcome.",
    }
    values.update(overrides)
    return ",".join(str(values[column]) for column in GROUND_TRUTH_HEADER.strip().split(",")) + "\n"


def test_ground_truth_evaluation_computes_confusion_matrix_and_readiness(
    tmp_path: Path,
):
    path = tmp_path / "ground_truth.csv"
    rows = []
    for index in range(1, 51):
        overrides: dict[str, object] = {}
        if index == 2:
            overrides = {
                "screening_class": "B",
                "deep_evidence_outcome": "not_viable",
                "actual_decision": "rejected",
            }
        elif index == 3:
            overrides = {
                "screening_class": "C",
                "deep_evidence_outcome": "viable",
                "actual_decision": "promoted",
            }
        elif index == 4:
            overrides = {
                "screening_class": "D",
                "deep_evidence_outcome": "not_viable",
                "actual_decision": "rejected",
            }
        if index > 15:
            overrides["deep_evidence_type"] = "none"
            overrides["deep_evidence_outcome"] = "inconclusive"
        if index > 25:
            overrides["region"] = "Bretagne"
            overrides["voltage_kv"] = "90"
        rows.append(_ground_truth_row(index, **overrides))
    path.write_text(GROUND_TRUTH_HEADER + "".join(rows), encoding="utf-8")

    metrics = evaluate_ground_truth(load_ground_truth_records(path))

    assert metrics.professionally_reviewed_site_count == 50
    assert metrics.deep_evidence_site_count == 15
    assert metrics.region_count == 2
    assert metrics.voltage_level_count == 2
    assert metrics.true_positive_count == 12
    assert metrics.false_positive_count == 1
    assert metrics.false_negative_count == 1
    assert metrics.true_negative_count == 1
    assert metrics.calibration_ready is True


def test_ground_truth_loader_rejects_invalid_class(tmp_path: Path):
    path = tmp_path / "ground_truth.csv"
    path.write_text(
        GROUND_TRUTH_HEADER + _ground_truth_row(1, screening_class="E"),
        encoding="utf-8",
    )

    with pytest.raises(CommercialValidationError, match="screening_class"):
        load_ground_truth_records(path)


def test_ground_truth_loader_rejects_conclusive_outcome_without_evidence(
    tmp_path: Path,
):
    path = tmp_path / "ground_truth.csv"
    path.write_text(
        GROUND_TRUTH_HEADER
        + _ground_truth_row(
            1,
            deep_evidence_type="none",
            deep_evidence_outcome="viable",
        ),
        encoding="utf-8",
    )

    with pytest.raises(CommercialValidationError, match="deep_evidence_outcome"):
        load_ground_truth_records(path)
