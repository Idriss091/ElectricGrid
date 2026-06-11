from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionFrontierPolicy:
    name: str
    max_p90_ratio: float
    max_energy_ratio: float
    max_event_hours: int
    max_event_mwh_per_mw: float
    conditional_max_event_mwh_per_mw: float | None = None


@dataclass(frozen=True)
class DecisionFrontierRow:
    bus_id: int
    bus_name: str
    policy: str
    qsts_p90_mw: float
    p90_curtailment_ratio: float
    weighted_curtailment_mwh: float
    curtailment_energy_ratio: float
    max_event_hours: int
    max_event_mwh: float
    max_event_mwh_per_mw: float
    frontier_verdict: str
    validation_level: str
    policy_definition: DecisionFrontierPolicy


DECISION_FRONTIER_POLICIES = (
    DecisionFrontierPolicy(
        "strict",
        max_p90_ratio=0.05,
        max_energy_ratio=0.0025,
        max_event_hours=6,
        max_event_mwh_per_mw=0.25,
    ),
    DecisionFrontierPolicy(
        "standard",
        max_p90_ratio=0.10,
        max_energy_ratio=0.01,
        max_event_hours=12,
        max_event_mwh_per_mw=1.0,
        conditional_max_event_mwh_per_mw=2.0,
    ),
    DecisionFrontierPolicy(
        "flexible",
        max_p90_ratio=0.25,
        max_energy_ratio=0.025,
        max_event_hours=48,
        max_event_mwh_per_mw=2.5,
    ),
    DecisionFrontierPolicy(
        "aggressive",
        max_p90_ratio=0.40,
        max_energy_ratio=0.05,
        max_event_hours=96,
        max_event_mwh_per_mw=5.0,
    ),
)


def frontier_verdict(
    p90_curtailment_ratio: float,
    curtailment_energy_ratio: float,
    max_event_hours: int,
    max_event_mwh_per_mw: float,
    policy: DecisionFrontierPolicy,
) -> str:
    if (
        p90_curtailment_ratio <= 1e-9
        and curtailment_energy_ratio <= 1e-9
        and max_event_hours == 0
        and max_event_mwh_per_mw <= 1e-9
    ):
        return "go"
    within_policy = _within_policy(
        p90_curtailment_ratio=p90_curtailment_ratio,
        curtailment_energy_ratio=curtailment_energy_ratio,
        max_event_hours=max_event_hours,
        max_event_mwh_per_mw=max_event_mwh_per_mw,
        policy=policy,
    )
    if within_policy and policy.name == "aggressive":
        flexible = next(item for item in DECISION_FRONTIER_POLICIES if item.name == "flexible")
        if not _within_policy(
            p90_curtailment_ratio=p90_curtailment_ratio,
            curtailment_energy_ratio=curtailment_energy_ratio,
            max_event_hours=max_event_hours,
            max_event_mwh_per_mw=max_event_mwh_per_mw,
            policy=flexible,
        ):
            return "investigate-only"
    if within_policy:
        return "go-with-conditions"
    if _within_conditional_event_policy(
        p90_curtailment_ratio=p90_curtailment_ratio,
        curtailment_energy_ratio=curtailment_energy_ratio,
        max_event_hours=max_event_hours,
        max_event_mwh_per_mw=max_event_mwh_per_mw,
        policy=policy,
    ):
        return "go-with-conditions"
    return "no-go"


def _within_policy(
    *,
    p90_curtailment_ratio: float,
    curtailment_energy_ratio: float,
    max_event_hours: int,
    max_event_mwh_per_mw: float,
    policy: DecisionFrontierPolicy,
) -> bool:
    return (
        p90_curtailment_ratio <= policy.max_p90_ratio + 1e-9
        and curtailment_energy_ratio <= policy.max_energy_ratio + 1e-9
        and max_event_hours <= policy.max_event_hours
        and max_event_mwh_per_mw <= policy.max_event_mwh_per_mw + 1e-9
    )


def _within_conditional_event_policy(
    *,
    p90_curtailment_ratio: float,
    curtailment_energy_ratio: float,
    max_event_hours: int,
    max_event_mwh_per_mw: float,
    policy: DecisionFrontierPolicy,
) -> bool:
    if policy.conditional_max_event_mwh_per_mw is None:
        return False
    return (
        p90_curtailment_ratio <= policy.max_p90_ratio + 1e-9
        and curtailment_energy_ratio <= policy.max_energy_ratio + 1e-9
        and max_event_hours <= policy.max_event_hours
        and max_event_mwh_per_mw <= policy.conditional_max_event_mwh_per_mw + 1e-9
    )


def decision_frontier_rows(
    *,
    bus_id: int,
    bus_name: str,
    requested_mw: float,
    qsts_p90_mw: float,
    weighted_curtailment_mwh: float,
    curtailment_energy_ratio: float,
    max_event_hours: int,
    max_event_mwh: float,
    validation_level: str,
) -> tuple[DecisionFrontierRow, ...]:
    p90_ratio = qsts_p90_mw / requested_mw if requested_mw > 0 else 0.0
    max_event_mwh_per_mw = max_event_mwh / requested_mw if requested_mw > 0 else 0.0
    return tuple(
        DecisionFrontierRow(
            bus_id=bus_id,
            bus_name=bus_name,
            policy=policy.name,
            qsts_p90_mw=round(qsts_p90_mw, 6),
            p90_curtailment_ratio=round(p90_ratio, 6),
            weighted_curtailment_mwh=round(weighted_curtailment_mwh, 6),
            curtailment_energy_ratio=round(curtailment_energy_ratio, 6),
            max_event_hours=max_event_hours,
            max_event_mwh=round(max_event_mwh, 6),
            max_event_mwh_per_mw=round(max_event_mwh_per_mw, 6),
            frontier_verdict=frontier_verdict(
                p90_curtailment_ratio=p90_ratio,
                curtailment_energy_ratio=curtailment_energy_ratio,
                max_event_hours=max_event_hours,
                max_event_mwh_per_mw=max_event_mwh_per_mw,
                policy=policy,
            ),
            validation_level=validation_level,
            policy_definition=policy,
        )
        for policy in DECISION_FRONTIER_POLICIES
    )
