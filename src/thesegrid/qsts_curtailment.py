from __future__ import annotations

from typing import Sequence

import pandas as pd

from thesegrid.models import CurtailmentEstimate
from thesegrid.risk import estimate_curtailment


def qsts_curtailment_estimate(
    hourly_records: pd.DataFrame,
    timestep_hours: float = 1.0,
) -> CurtailmentEstimate:
    if hourly_records.empty:
        return estimate_curtailment(())
    worst_by_timestamp = hourly_records.groupby("timestamp")["curtailed_mw"].max()
    return estimate_curtailment(worst_by_timestamp.tolist(), timestep_hours=timestep_hours)


def weighted_qsts_curtailment_estimate(
    hourly_records: pd.DataFrame,
    timestamp_weights: dict[str, float],
) -> CurtailmentEstimate:
    if hourly_records.empty:
        return estimate_curtailment(())
    worst_by_timestamp = hourly_records.groupby("timestamp")["curtailed_mw"].max()
    weighted_mwh = 0.0
    weighted_hours = 0.0
    weighted_values: list[tuple[float, float]] = []
    for timestamp, curtailed_mw in worst_by_timestamp.items():
        weight = timestamp_weights.get(str(timestamp), 1.0)
        positive_curtailment = max(0.0, float(curtailed_mw))
        weighted_mwh += positive_curtailment * weight
        if positive_curtailment > 0.0:
            weighted_hours += weight
        weighted_values.append((positive_curtailment, weight))
    base = estimate_curtailment(worst_by_timestamp.tolist())
    if _uses_non_uniform_weights(weighted_values):
        p50_mw = _weighted_quantile(weighted_values, 0.50)
        p90_mw = _weighted_quantile(weighted_values, 0.90)
    else:
        p50_mw = base.p50_mw
        p90_mw = base.p90_mw
    return CurtailmentEstimate(
        expected_hours=int(round(weighted_hours)),
        expected_mwh=round(weighted_mwh, 6),
        p50_mw=p50_mw,
        p90_mw=p90_mw,
    )


def _uses_non_uniform_weights(weighted_values: Sequence[tuple[float, float]]) -> bool:
    if not weighted_values:
        return False
    first_weight = weighted_values[0][1]
    return any(abs(weight - first_weight) > 1e-9 for _value, weight in weighted_values)


def _weighted_quantile(weighted_values: Sequence[tuple[float, float]], quantile: float) -> float:
    positive_weights = [(value, weight) for value, weight in weighted_values if weight > 0.0]
    if not positive_weights:
        return 0.0
    total_weight = sum(weight for _value, weight in positive_weights)
    threshold = quantile * total_weight
    cumulative = 0.0
    for value, weight in sorted(positive_weights, key=lambda item: item[0]):
        cumulative += weight
        if cumulative >= threshold:
            return round(value, 6)
    return round(positive_weights[-1][0], 6)
