from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from thesegrid.constraints import ConstraintSettings, check_constraints
from thesegrid.models import ConstraintViolation, Direction
from thesegrid.networks import ToyNetwork


@dataclass(frozen=True)
class DispatchEvaluation:
    feasible: bool
    violations: tuple[ConstraintViolation, ...]


@dataclass(frozen=True)
class FirmCapacityResult:
    injection_mw: float
    withdrawal_mw: float
    binding_constraints: tuple[ConstraintViolation, ...]

    @property
    def firm_capacity_mw(self) -> float:
        return min(self.injection_mw, self.withdrawal_mw)


def find_max_feasible(
    upper_mw: float,
    is_feasible: Callable[[float], bool],
    tolerance_mw: float = 0.05,
    max_iterations: int = 40,
) -> float:
    if upper_mw < 0:
        raise ValueError("upper_mw must be non-negative")
    if tolerance_mw <= 0:
        raise ValueError("tolerance_mw must be positive")
    if upper_mw == 0:
        return 0.0

    low = 0.0
    high = upper_mw
    if is_feasible(high):
        return high

    for _ in range(max_iterations):
        if high - low <= tolerance_mw:
            break
        midpoint = (low + high) / 2
        if is_feasible(midpoint):
            low = midpoint
        else:
            high = midpoint
    return low


def estimate_firm_capacity(
    net: object,
    bus_id: int,
    requested_mw: float,
    settings: ConstraintSettings,
    tolerance_mw: float = 0.05,
) -> FirmCapacityResult:
    if bus_id not in net.bus.index:
        raise ValueError(f"bus_id {bus_id} is not present in the network")

    injection = find_max_feasible(
        upper_mw=requested_mw,
        is_feasible=lambda mw: evaluate_dispatch(net, bus_id, "injection", mw, settings).feasible,
        tolerance_mw=tolerance_mw,
    )
    withdrawal = find_max_feasible(
        upper_mw=requested_mw,
        is_feasible=lambda mw: evaluate_dispatch(net, bus_id, "withdrawal", mw, settings).feasible,
        tolerance_mw=tolerance_mw,
    )
    binding_constraints = _merge_constraints(
        evaluate_dispatch(net, bus_id, "injection", requested_mw, settings).violations,
        evaluate_dispatch(net, bus_id, "withdrawal", requested_mw, settings).violations,
    )
    return FirmCapacityResult(
        injection_mw=injection,
        withdrawal_mw=withdrawal,
        binding_constraints=binding_constraints,
    )


def evaluate_dispatch(
    net: object,
    bus_id: int,
    direction: Direction,
    mw: float,
    settings: ConstraintSettings,
) -> DispatchEvaluation:
    if isinstance(net, ToyNetwork):
        return _evaluate_toy_dispatch(net, bus_id, direction, mw, settings)

    import pandapower as pp

    working_net = deepcopy(net)
    if mw > 0:
        if direction == "injection":
            pp.create_sgen(
                working_net,
                bus=bus_id,
                p_mw=mw,
                q_mvar=0.0,
                name="candidate_bess_injection",
            )
        else:
            pp.create_load(
                working_net,
                bus=bus_id,
                p_mw=mw,
                q_mvar=0.0,
                name="candidate_bess_withdrawal",
            )

    try:
        pp.runpp(working_net, numba=False)
    except Exception:
        return DispatchEvaluation(
            feasible=False,
            violations=(
                ConstraintViolation(
                    element_type="power_flow",
                    element_id=-1,
                    element_name="pandapower",
                    metric="converged",
                    value=0.0,
                    limit=1.0,
                ),
            ),
        )

    violations = tuple(check_constraints(working_net, settings))
    return DispatchEvaluation(feasible=not violations, violations=violations)


def _evaluate_toy_dispatch(
    net: ToyNetwork,
    bus_id: int,
    direction: Direction,
    mw: float,
    settings: ConstraintSettings,
) -> DispatchEvaluation:
    if bus_id not in net.bus.index:
        raise ValueError(f"bus_id {bus_id} is not present in the network")
    del direction
    loading_percent = ((net.base_load_mw + mw) / net.line_limit_mw) * 100
    voltage_drop = mw * net.voltage_drop_pu_per_mw
    min_vm_pu = 1.0 - voltage_drop
    max_vm_pu = 1.0 + voltage_drop
    violations: list[ConstraintViolation] = []
    if loading_percent > settings.max_loading_percent:
        violations.append(
            ConstraintViolation(
                element_type="line",
                element_id=0,
                element_name="slack-candidate",
                metric="line.loading_percent",
                value=loading_percent,
                limit=settings.max_loading_percent,
            )
        )
    if min_vm_pu < settings.min_vm_pu:
        violations.append(
            ConstraintViolation(
                element_type="bus",
                element_id=bus_id,
                element_name="candidate",
                metric="bus.vm_pu.min",
                value=min_vm_pu,
                limit=settings.min_vm_pu,
            )
        )
    if max_vm_pu > settings.max_vm_pu:
        violations.append(
            ConstraintViolation(
                element_type="bus",
                element_id=bus_id,
                element_name="candidate",
                metric="bus.vm_pu.max",
                value=max_vm_pu,
                limit=settings.max_vm_pu,
            )
        )
    return DispatchEvaluation(feasible=not violations, violations=tuple(violations))


def _merge_constraints(
    left: tuple[ConstraintViolation, ...],
    right: tuple[ConstraintViolation, ...],
) -> tuple[ConstraintViolation, ...]:
    seen: set[tuple[str, int, str]] = set()
    merged: list[ConstraintViolation] = []
    for violation in (*left, *right):
        key = (violation.element_type, violation.element_id, violation.metric)
        if key in seen:
            continue
        seen.add(key)
        merged.append(violation)
    return tuple(merged)
