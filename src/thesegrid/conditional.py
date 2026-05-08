from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from thesegrid.gabarits import GabaritKind, is_restricted
from thesegrid.risk import estimate_curtailment


@dataclass(frozen=True)
class EnvelopeAssessment:
    name: str
    conditional_capacity_mw: float
    curtailment_mw: tuple[float, ...]

    @property
    def expected_mwh(self) -> float:
        return estimate_curtailment(self.curtailment_mw).expected_mwh


def recommend_envelope(
    requested_mw: float,
    firm_injection_mw: float,
    firm_withdrawal_mw: float,
    timestamps: tuple[datetime, ...],
) -> EnvelopeAssessment:
    firm_capacity_mw = min(firm_injection_mw, firm_withdrawal_mw)
    if requested_mw <= firm_capacity_mw + 1e-9:
        return EnvelopeAssessment(
            name=GabaritKind.FIRM_ONLY.value,
            conditional_capacity_mw=requested_mw,
            curtailment_mw=tuple(0.0 for _ in timestamps),
        )

    candidates = [
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
    return min(candidates, key=lambda candidate: candidate.expected_mwh)


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
