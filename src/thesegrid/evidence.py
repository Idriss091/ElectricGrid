from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


EvidenceLevel = Literal["screening_only", "qsts_short", "qsts_stratified", "qsts_full_year"]
DataSourceType = Literal["benchmark", "client_model", "public_reconstruction", "operator_validated"]

EVIDENCE_LEVELS = ("screening_only", "qsts_short", "qsts_stratified", "qsts_full_year")
DATA_SOURCE_TYPES = ("benchmark", "client_model", "public_reconstruction", "operator_validated")


@dataclass(frozen=True)
class EvidenceProfile:
    evidence_level: EvidenceLevel
    data_source_type: DataSourceType
    decision_confidence: str
    recommended_next_action: str
    commercial_use: str


def evidence_profile(
    *,
    evidence_level: str,
    data_source_type: str,
) -> EvidenceProfile:
    if evidence_level not in EVIDENCE_LEVELS:
        raise ValueError("evidence_level must be a supported Thesegrid evidence level")
    if data_source_type not in DATA_SOURCE_TYPES:
        raise ValueError("data_source_type must be a supported Thesegrid data source type")

    return EvidenceProfile(
        evidence_level=evidence_level,  # type: ignore[arg-type]
        data_source_type=data_source_type,  # type: ignore[arg-type]
        decision_confidence=_decision_confidence(evidence_level),
        recommended_next_action=_recommended_next_action(evidence_level),
        commercial_use=_commercial_use(evidence_level, data_source_type),
    )


def _decision_confidence(evidence_level: str) -> str:
    if evidence_level == "qsts_full_year":
        return "high"
    if evidence_level == "qsts_stratified":
        return "medium"
    return "low"


def _recommended_next_action(evidence_level: str) -> str:
    if evidence_level == "qsts_full_year":
        return "prepare_investor_memo"
    if evidence_level == "qsts_stratified":
        return "run_full_year_validation"
    return "run_qsts_validation"


def _commercial_use(evidence_level: str, data_source_type: str) -> str:
    if data_source_type == "benchmark":
        return "benchmark_workflow_evidence_only"
    if data_source_type == "operator_validated" and evidence_level == "qsts_full_year":
        return "operator_validated_pre_feasibility_evidence"
    if data_source_type in {"client_model", "public_reconstruction"}:
        return "client_pre_feasibility_evidence"
    return "technical_screening_evidence"
