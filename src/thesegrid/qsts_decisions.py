from __future__ import annotations

from typing import Any

from thesegrid.models import CurtailmentEstimate


def qsts_verdict(
    curtailment: CurtailmentEstimate,
    p90_tolerance_mw: float,
    mwh_tolerance: float,
) -> str:
    if curtailment.p90_mw <= 1e-9 and curtailment.expected_mwh <= 1e-9:
        return "go"
    if (
        curtailment.p90_mw <= p90_tolerance_mw + 1e-9
        and curtailment.expected_mwh <= mwh_tolerance + 1e-9
    ):
        return "go-with-conditions"
    return "no-go"


def qsts_verdict_driver(
    curtailment: CurtailmentEstimate,
    p90_tolerance_mw: float,
    mwh_tolerance: float,
) -> str:
    if curtailment.p90_mw <= 1e-9 and curtailment.expected_mwh <= 1e-9:
        return "no_curtailment"
    p90_exceeds = curtailment.p90_mw > p90_tolerance_mw + 1e-9
    mwh_exceeds = curtailment.expected_mwh > mwh_tolerance + 1e-9
    if p90_exceeds and mwh_exceeds:
        return "both_exceed"
    if p90_exceeds:
        return "p90_exceeds_tolerance"
    if mwh_exceeds:
        return "mwh_exceeds_tolerance"
    return "within_tolerance"


def validation_level(request: Any, evaluated_time_steps: int | None = None) -> str:
    if request.stratified_sample:
        return "qsts_stratified"
    if (
        evaluated_time_steps is not None
        and evaluated_time_steps >= 8760
        and request.sample_every_n_hours == 1
    ):
        return "qsts_full_year"
    return "qsts_short"


def decision_confidence(request: Any, evaluated_time_steps: int | None = None) -> str:
    level = validation_level(request, evaluated_time_steps)
    if level == "qsts_full_year":
        return "high"
    if level == "qsts_stratified":
        return "medium"
    return "low"


def recommended_next_action(
    qsts_verdict: str,
    verdict_driver: str,
    request: Any,
    evaluated_time_steps: int | None = None,
) -> str:
    if validation_level(request, evaluated_time_steps) != "qsts_full_year":
        if qsts_verdict == "no-go":
            return "resize_or_run_full_year_validation"
        return "run_full_year_validation"
    if qsts_verdict == "go":
        return "proceed_to_investor_memo"
    if qsts_verdict == "go-with-conditions":
        return "proceed_with_conditions"
    if verdict_driver == "mwh_exceeds_tolerance":
        return "reject_or_resize_connection"
    return "reject_or_resize_connection"
