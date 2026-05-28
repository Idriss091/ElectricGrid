import pytest

from thesegrid.evidence import EvidenceProfile, evidence_profile


def test_screening_benchmark_evidence_profile_sets_low_confidence_and_next_action():
    profile = evidence_profile(
        evidence_level="screening_only",
        data_source_type="benchmark",
    )

    assert profile == EvidenceProfile(
        evidence_level="screening_only",
        data_source_type="benchmark",
        decision_confidence="low",
        recommended_next_action="run_qsts_validation",
        commercial_use="benchmark_workflow_evidence_only",
    )


def test_full_year_client_model_evidence_profile_is_pilot_grade():
    profile = evidence_profile(
        evidence_level="qsts_full_year",
        data_source_type="client_model",
    )

    assert profile.decision_confidence == "high"
    assert profile.recommended_next_action == "prepare_investor_memo"
    assert profile.commercial_use == "client_pre_feasibility_evidence"


def test_evidence_profile_rejects_unknown_values():
    with pytest.raises(ValueError, match="evidence_level"):
        evidence_profile(evidence_level="qsts_weekend", data_source_type="benchmark")

    with pytest.raises(ValueError, match="data_source_type"):
        evidence_profile(evidence_level="screening_only", data_source_type="spreadsheet")
