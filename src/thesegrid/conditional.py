from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from thesegrid.capacity import find_max_feasible
from thesegrid.gabarits import GabaritKind, is_restricted
from thesegrid.models import CurtailmentEstimate, EnvelopeOption
from thesegrid.risk import estimate_curtailment


@dataclass(frozen=True)
class EnvelopeAssessment:
    name: str
    evaluated_mw: float
    conditional_capacity_mw: float
    curtailment_mw: tuple[float, ...]
    alternatives: tuple[EnvelopeOption, ...] = ()

    @property
    def expected_mwh(self) -> float:
        return estimate_curtailment(self.curtailment_mw).expected_mwh


def recommend_envelope(
    requested_mw: float,
    firm_injection_mw: float,
    firm_withdrawal_mw: float,
    timestamps: tuple[datetime, ...],
    p90_tolerance_mw: float = 0.0,
    curtailment_tolerance_mwh: float = 0.0,
    is_economically_viable: Callable[[float, CurtailmentEstimate], bool] | None = None,
    tolerance_mw: float = 0.05,
) -> EnvelopeAssessment:
    firm_capacity_mw = min(firm_injection_mw, firm_withdrawal_mw)
    candidate = _best_envelope(
        requested_mw,
        firm_injection_mw,
        firm_withdrawal_mw,
        timestamps,
    )
    conditional_capacity_mw = find_max_feasible(
        upper_mw=requested_mw,
        is_feasible=lambda mw: _is_conditionally_acceptable(
            mw=mw,
            firm_injection_mw=firm_injection_mw,
            firm_withdrawal_mw=firm_withdrawal_mw,
            firm_capacity_mw=firm_capacity_mw,
            timestamps=timestamps,
            p90_tolerance_mw=p90_tolerance_mw,
            curtailment_tolerance_mwh=curtailment_tolerance_mwh,
            is_economically_viable=is_economically_viable,
        ),
        tolerance_mw=tolerance_mw,
    )
    return EnvelopeAssessment(
        name=candidate.name,
        evaluated_mw=requested_mw,
        conditional_capacity_mw=conditional_capacity_mw,
        curtailment_mw=candidate.curtailment_mw,
        alternatives=_envelope_options(
            requested_mw,
            firm_injection_mw,
            firm_withdrawal_mw,
            timestamps,
        ),
    )


def _is_conditionally_acceptable(
    mw: float,
    firm_injection_mw: float,
    firm_withdrawal_mw: float,
    firm_capacity_mw: float,
    timestamps: tuple[datetime, ...],
    p90_tolerance_mw: float,
    curtailment_tolerance_mwh: float,
    is_economically_viable: Callable[[float, CurtailmentEstimate], bool] | None,
) -> bool:
    envelope = _best_envelope(mw, firm_injection_mw, firm_withdrawal_mw, timestamps)
    curtailment = estimate_curtailment(envelope.curtailment_mw)
    if mw <= firm_capacity_mw + 1e-9 and curtailment.p90_mw <= 1e-9:
        return True
    if curtailment.p90_mw > p90_tolerance_mw + 1e-9:
        return False
    if curtailment_tolerance_mwh > 0 and curtailment.expected_mwh > curtailment_tolerance_mwh:
        return False
    if is_economically_viable is None:
        return True
    return is_economically_viable(mw, curtailment)


def _best_envelope(
    requested_mw: float,
    firm_injection_mw: float,
    firm_withdrawal_mw: float,
    timestamps: tuple[datetime, ...],
) -> EnvelopeAssessment:
    firm_capacity_mw = min(firm_injection_mw, firm_withdrawal_mw)
    if requested_mw <= firm_capacity_mw + 1e-9:
        return EnvelopeAssessment(
            name=GabaritKind.FIRM_ONLY.value,
            evaluated_mw=requested_mw,
            conditional_capacity_mw=requested_mw,
            curtailment_mw=tuple(0.0 for _ in timestamps),
        )

    candidates = tuple(
        _assess_gabarit(
            requested_mw,
            firm_injection_mw,
            firm_withdrawal_mw,
            timestamps,
            gabarit,
        )
        for gabarit in (
            GabaritKind.RTE_INJECTION,
            GabaritKind.RTE_WITHDRAWAL,
            GabaritKind.CUSTOM,
        )
    )
    return min(candidates, key=lambda candidate: candidate.expected_mwh)


def _envelope_options(
    requested_mw: float,
    firm_injection_mw: float,
    firm_withdrawal_mw: float,
    timestamps: tuple[datetime, ...],
) -> tuple[EnvelopeOption, ...]:
    firm_capacity_mw = min(firm_injection_mw, firm_withdrawal_mw)
    assessments = [
        EnvelopeAssessment(
            name=GabaritKind.FIRM_ONLY.value,
            evaluated_mw=requested_mw,
            conditional_capacity_mw=min(requested_mw, firm_capacity_mw),
            curtailment_mw=tuple(
                max(requested_mw - firm_capacity_mw, 0.0) for _ in timestamps
            ),
        ),
        _assess_gabarit(
            requested_mw,
            firm_injection_mw,
            firm_withdrawal_mw,
            timestamps,
            GabaritKind.RTE_INJECTION,
        ),
        _assess_gabarit(
            requested_mw,
            firm_injection_mw,
            firm_withdrawal_mw,
            timestamps,
            GabaritKind.RTE_WITHDRAWAL,
        ),
        _assess_gabarit(
            requested_mw,
            firm_injection_mw,
            firm_withdrawal_mw,
            timestamps,
            GabaritKind.CUSTOM,
        ),
    ]
    options: list[EnvelopeOption] = []
    for assessment in assessments:
        curtailment = estimate_curtailment(assessment.curtailment_mw)
        options.append(
            EnvelopeOption(
                name=assessment.name,
                evaluated_mw=round(assessment.evaluated_mw, 6),
                expected_curtailment_hours=curtailment.expected_hours,
                expected_curtailment_mwh=curtailment.expected_mwh,
                p50_curtailment_mw=curtailment.p50_mw,
                p90_curtailment_mw=curtailment.p90_mw,
            )
        )
    return tuple(options)


def _assess_gabarit(
    requested_mw: float,
    firm_injection_mw: float,
    firm_withdrawal_mw: float,
    timestamps: tuple[datetime, ...],
    gabarit: GabaritKind,
) -> EnvelopeAssessment:
    curtailed: list[float] = []
    for timestamp in timestamps:
        injection_allowed = _allowed_directional_mw(
            requested_mw,
            firm_injection_mw,
            timestamp,
            "injection",
            gabarit,
        )
        withdrawal_allowed = _allowed_directional_mw(
            requested_mw,
            firm_withdrawal_mw,
            timestamp,
            "withdrawal",
            gabarit,
        )
        curtailed.append(
            max(requested_mw - injection_allowed, requested_mw - withdrawal_allowed, 0.0)
        )
    return EnvelopeAssessment(
        name=gabarit.value,
        evaluated_mw=requested_mw,
        conditional_capacity_mw=requested_mw,
        curtailment_mw=tuple(curtailed),
    )


def _allowed_directional_mw(
    requested_mw: float,
    firm_directional_mw: float,
    timestamp: datetime,
    direction: str,
    gabarit: GabaritKind,
) -> float:
    if direction in {"injection", "withdrawal"} and is_restricted(timestamp, direction, gabarit):
        return 0.0
    return min(requested_mw, firm_directional_mw)
