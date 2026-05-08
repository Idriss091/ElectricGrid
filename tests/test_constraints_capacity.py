from types import SimpleNamespace

import pandas as pd

from thesegrid.capacity import find_max_feasible
from thesegrid.constraints import ConstraintSettings, check_constraints


def test_check_constraints_reports_voltage_and_loading_violations():
    net = SimpleNamespace(
        converged=True,
        res_bus=pd.DataFrame({"vm_pu": [1.06, 0.94, 1.0]}),
        bus=pd.DataFrame({"name": ["slack", "candidate", "other"]}),
        res_line=pd.DataFrame({"loading_percent": [101.0, 20.0]}),
        line=pd.DataFrame({"name": ["line-a", "line-b"]}),
        res_trafo=pd.DataFrame({"loading_percent": [99.0]}),
        trafo=pd.DataFrame({"name": ["trafo-a"]}),
    )

    violations = check_constraints(net, ConstraintSettings())

    assert [violation.metric for violation in violations] == [
        "bus.vm_pu.max",
        "bus.vm_pu.min",
        "line.loading_percent",
    ]
    assert violations[0].element_name == "slack"
    assert violations[2].element_name == "line-a"


def test_find_max_feasible_uses_binary_search_until_tolerance():
    result = find_max_feasible(
        upper_mw=10.0,
        is_feasible=lambda mw: mw <= 7.3,
        tolerance_mw=0.05,
    )

    assert 7.25 <= result <= 7.3
