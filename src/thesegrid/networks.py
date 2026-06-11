from __future__ import annotations

import builtins
from contextlib import contextmanager
from dataclasses import dataclass
from types import ModuleType
from typing import Iterator

import pandas as pd


@dataclass(frozen=True)
class ToyNetwork:
    """Small deterministic network used for smoke tests when SimBench is unavailable."""

    name: str
    bus: pd.DataFrame
    base_load_mw: float = 0.2
    line_limit_mw: float = 5.0
    voltage_drop_pu_per_mw: float = 0.002


def load_network(network_code: str) -> object:
    """Load a network by code.

    ``toy`` is a tiny deterministic network for smoke tests and examples. Any other
    code is passed to SimBench.
    """
    if network_code == "toy":
        return _toy_network()

    try:
        with _disable_optional_ortools_import():
            import simbench as sb
    except ImportError as exc:
        raise ImportError(
            "SimBench is required for non-toy networks. Install the project dependency "
            "with `pip install -e .` before using SimBench codes."
        ) from exc
    return sb.get_simbench_net(network_code)


@contextmanager
def _disable_optional_ortools_import() -> Iterator[None]:
    """Make pandapower fall back to scipy instead of importing optional OR-Tools.

    Some Python environments abort inside the optional OR-Tools native extension during
    pandapower import. VoltPath does not use pandapower's OR-Tools estimation path for
    screening or QSTS, so raising ImportError for that optional module is safer than
    letting the process crash before SimBench can load.
    """

    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> ModuleType:
        if name == "ortools.linear_solver" or name.startswith("ortools.linear_solver."):
            raise ImportError("optional OR-Tools import disabled for pandapower loading")
        return original_import(name, globals, locals, fromlist, level)

    builtins.__import__ = guarded_import
    try:
        yield
    finally:
        builtins.__import__ = original_import


def _toy_network() -> ToyNetwork:
    bus = pd.DataFrame(
        {
            "name": ["slack", "candidate"],
            "vn_kv": [110.0, 20.0],
            "in_service": [True, True],
        },
        index=[0, 1],
    )
    return ToyNetwork(name="thesegrid-toy", bus=bus)


def _pandapower_toy_network() -> object:
    import pandapower as pp

    net = pp.create_empty_network(name="thesegrid-toy")
    slack = pp.create_bus(net, vn_kv=20.0, name="slack")
    candidate = pp.create_bus(net, vn_kv=20.0, name="candidate")
    pp.create_ext_grid(net, slack, vm_pu=1.0)
    pp.create_line_from_parameters(
        net,
        from_bus=slack,
        to_bus=candidate,
        length_km=1.0,
        r_ohm_per_km=0.08,
        x_ohm_per_km=0.08,
        c_nf_per_km=0.0,
        max_i_ka=0.35,
        name="slack-candidate",
    )
    pp.create_load(net, bus=candidate, p_mw=0.2, q_mvar=0.02, name="base_load")
    return net
