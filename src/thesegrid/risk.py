from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from thesegrid.models import CurtailmentEstimate


def estimate_curtailment(
    curtailment_mw: Sequence[float],
    timestep_hours: float = 1.0,
) -> CurtailmentEstimate:
    if timestep_hours <= 0:
        raise ValueError("timestep_hours must be positive")
    values = np.array([max(0.0, float(value)) for value in curtailment_mw], dtype=float)
    if values.size == 0:
        return CurtailmentEstimate(expected_hours=0, expected_mwh=0.0, p50_mw=0.0, p90_mw=0.0)

    expected_hours = int(np.count_nonzero(values > 0.0))
    expected_mwh = float(values.sum() * timestep_hours)
    return CurtailmentEstimate(
        expected_hours=expected_hours,
        expected_mwh=round(expected_mwh, 6),
        p50_mw=round(float(np.percentile(values, 50)), 6),
        p90_mw=round(float(np.percentile(values, 90)), 6),
    )
