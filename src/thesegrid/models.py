from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["injection", "withdrawal"]
Verdict = Literal["go", "no-go", "go-with-conditions"]


@dataclass(frozen=True)
class EconomicAssumptions:
    """Configurable proxies for the techno-economic comparison."""

    gross_margin_eur_per_mwh: float = 0.0
    curtailment_penalty_eur_per_mwh: float = 100.0
    waiting_cost_eur_per_mw_year: float = 50_000.0

    def __post_init__(self) -> None:
        if self.gross_margin_eur_per_mwh < 0:
            raise ValueError("gross_margin_eur_per_mwh must be non-negative")
        if self.curtailment_penalty_eur_per_mwh < 0:
            raise ValueError("curtailment_penalty_eur_per_mwh must be non-negative")
        if self.waiting_cost_eur_per_mw_year < 0:
            raise ValueError("waiting_cost_eur_per_mw_year must be non-negative")


@dataclass(frozen=True)
class ConnectionRequest:
    """Input contract for a BESS flexible-connection pre-feasibility run."""

    network_code: str
    bus_id: int
    requested_mw: float
    asset: str = "bess"
    curtailment_tolerance_mwh_per_year: float = 0.0
    p90_curtailment_tolerance_mw: float = 0.0
    reinforcement_wait_years: float = 5.0
    economics: EconomicAssumptions = field(default_factory=EconomicAssumptions)

    def __post_init__(self) -> None:
        if not self.network_code:
            raise ValueError("network_code must not be empty")
        if self.requested_mw <= 0:
            raise ValueError("requested_mw must be positive")
        if self.bus_id < 0:
            raise ValueError("bus_id must be non-negative")
        if self.asset.lower() != "bess":
            raise ValueError("V1 supports BESS assets only")
        if self.curtailment_tolerance_mwh_per_year < 0:
            raise ValueError("curtailment_tolerance_mwh_per_year must be non-negative")
        if self.p90_curtailment_tolerance_mw < 0:
            raise ValueError("p90_curtailment_tolerance_mw must be non-negative")
        if self.reinforcement_wait_years < 0:
            raise ValueError("reinforcement_wait_years must be non-negative")


@dataclass(frozen=True)
class ConstraintViolation:
    element_type: str
    element_id: int
    element_name: str
    metric: str
    value: float
    limit: float

    @property
    def description(self) -> str:
        return (
            f"{self.element_type}[{self.element_id}] {self.element_name} "
            f"{self.metric}={self.value:.3f} limit={self.limit:.3f}"
        )


@dataclass(frozen=True)
class CurtailmentEstimate:
    expected_hours: int
    expected_mwh: float
    p50_mw: float
    p90_mw: float


@dataclass(frozen=True)
class EconomicComparison:
    served_energy_mwh: float
    connect_now_gross_margin_eur: float
    ebitda_at_risk_eur: float
    waiting_cost_avoided_eur: float
    flexible_value_delta_eur: float


@dataclass(frozen=True)
class EnvelopeOption:
    name: str
    evaluated_mw: float
    expected_curtailment_hours: int
    expected_curtailment_mwh: float
    p50_curtailment_mw: float
    p90_curtailment_mw: float


@dataclass(frozen=True)
class InvestmentMemo:
    request: ConnectionRequest
    firm_injection_mw: float
    firm_withdrawal_mw: float
    firm_capacity_mw: float
    conditional_capacity_mw: float
    evaluated_conditional_mw: float
    recommended_envelope: str
    envelope_options: tuple[EnvelopeOption, ...]
    curtailment: CurtailmentEstimate
    economics: EconomicComparison
    binding_constraints: tuple[ConstraintViolation, ...]
    verdict: Verdict
    assumptions: tuple[str, ...]
    scientific_uncertainty: tuple[str, ...]
