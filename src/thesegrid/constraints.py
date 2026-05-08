from __future__ import annotations

from dataclasses import dataclass
from math import isnan
from typing import Any

from thesegrid.models import ConstraintViolation


@dataclass(frozen=True)
class ConstraintSettings:
    min_vm_pu: float = 0.95
    max_vm_pu: float = 1.05
    max_loading_percent: float = 100.0


def check_constraints(net: Any, settings: ConstraintSettings) -> list[ConstraintViolation]:
    """Inspect pandapower-style result tables for V1 steady-state violations."""
    violations: list[ConstraintViolation] = []
    if getattr(net, "converged", True) is False:
        violations.append(
            ConstraintViolation(
                element_type="power_flow",
                element_id=-1,
                element_name="pandapower",
                metric="converged",
                value=0.0,
                limit=1.0,
            )
        )
        return violations

    violations.extend(_bus_voltage_violations(net, settings))
    violations.extend(_loading_violations(net, "line", settings.max_loading_percent))
    violations.extend(_loading_violations(net, "trafo", settings.max_loading_percent))
    violations.extend(_loading_violations(net, "trafo3w", settings.max_loading_percent))
    return violations


def _bus_voltage_violations(net: Any, settings: ConstraintSettings) -> list[ConstraintViolation]:
    result_table = getattr(net, "res_bus", None)
    if result_table is None or "vm_pu" not in result_table:
        return []

    violations: list[ConstraintViolation] = []
    for bus_id, row in result_table.iterrows():
        value = float(row["vm_pu"])
        if isnan(value):
            continue
        element_name = _element_name(net, "bus", int(bus_id))
        if value > settings.max_vm_pu:
            violations.append(
                ConstraintViolation(
                    element_type="bus",
                    element_id=int(bus_id),
                    element_name=element_name,
                    metric="bus.vm_pu.max",
                    value=value,
                    limit=settings.max_vm_pu,
                )
            )
        elif value < settings.min_vm_pu:
            violations.append(
                ConstraintViolation(
                    element_type="bus",
                    element_id=int(bus_id),
                    element_name=element_name,
                    metric="bus.vm_pu.min",
                    value=value,
                    limit=settings.min_vm_pu,
                )
            )
    return violations


def _loading_violations(
    net: Any,
    element_type: str,
    max_loading_percent: float,
) -> list[ConstraintViolation]:
    result_table = getattr(net, f"res_{element_type}", None)
    if result_table is None or "loading_percent" not in result_table:
        return []

    violations: list[ConstraintViolation] = []
    for element_id, row in result_table.iterrows():
        value = float(row["loading_percent"])
        if isnan(value) or value <= max_loading_percent:
            continue
        violations.append(
            ConstraintViolation(
                element_type=element_type,
                element_id=int(element_id),
                element_name=_element_name(net, element_type, int(element_id)),
                metric=f"{element_type}.loading_percent",
                value=value,
                limit=max_loading_percent,
            )
        )
    return violations


def _element_name(net: Any, element_type: str, element_id: int) -> str:
    table = getattr(net, element_type, None)
    if table is None or "name" not in table or element_id not in table.index:
        return ""
    value = table.at[element_id, "name"]
    return "" if value is None else str(value)
