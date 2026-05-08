from __future__ import annotations

from dataclasses import dataclass

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
        import simbench as sb
    except ImportError as exc:
        raise ImportError(
            "SimBench is required for non-toy networks. Install the project dependency "
            "with `pip install -e .` before using SimBench codes."
        ) from exc
    return sb.get_simbench_net(network_code)


def _toy_network() -> ToyNetwork:
    bus = pd.DataFrame({"name": ["slack", "candidate"]}, index=[0, 1])
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
