from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import numpy as np

from thesegrid.models import Direction


TIME_BLOCKS = (
    (0, 7, "00-07"),
    (7, 10, "07-10"),
    (10, 13, "10-13"),
    (13, 17, "13-17"),
    (17, 18, "17-18"),
    (18, 21, "18-21"),
    (21, 24, "21-24"),
)


class EnvelopeRecordLike(Protocol):
    timestamp: str
    bus_id: int
    bus_name: str
    direction: Direction
    allowed_mw: float
    curtailed_mw: float
    incremental_binding_constraint: str


@dataclass(frozen=True)
class ContractualEnvelopeRequest:
    """V1 synthesis settings for compact investor-facing BESS envelopes."""

    allowed_quantile: float = 0.10

    def __post_init__(self) -> None:
        if not 0.0 <= self.allowed_quantile <= 1.0:
            raise ValueError("allowed_quantile must be between 0 and 1")


@dataclass(frozen=True)
class ContractualEnvelopeRow:
    bus_id: int
    bus_name: str
    direction: Direction
    season: str
    time_block: str
    allowed_mw_p10: float
    allowed_mw_p25: float
    allowed_mw_p50: float
    allowed_mw_min: float
    curtailed_mw_p90: float
    dominant_incremental_constraint: str


@dataclass(frozen=True)
class ContractualEnvelopeResult:
    rows: tuple[ContractualEnvelopeRow, ...]
    method: str = "RTE-inspired V1 season/time-block synthesis using P10 allowed MW"


def synthesize_contractual_envelope(
    records: tuple[EnvelopeRecordLike, ...],
    request: ContractualEnvelopeRequest | None = None,
) -> ContractualEnvelopeResult:
    request = request or ContractualEnvelopeRequest()
    groups: dict[tuple[int, str, Direction, str, str], list[EnvelopeRecordLike]] = {}
    for record in records:
        direction = _direction(record.direction)
        timestamp = _datetime_from_timestamp(record.timestamp)
        key = (
            int(record.bus_id),
            str(record.bus_name),
            direction,
            _season(timestamp.month, direction),
            _time_block(timestamp.hour),
        )
        groups.setdefault(key, []).append(record)

    rows: list[ContractualEnvelopeRow] = []
    for key, group in sorted(groups.items(), key=lambda item: item[0]):
        bus_id, bus_name, direction, season, time_block = key
        allowed = np.array([max(0.0, float(record.allowed_mw)) for record in group], dtype=float)
        curtailed = np.array([max(0.0, float(record.curtailed_mw)) for record in group], dtype=float)
        rows.append(
            ContractualEnvelopeRow(
                bus_id=bus_id,
                bus_name=bus_name,
                direction=direction,
                season=season,
                time_block=time_block,
                allowed_mw_p10=round(float(np.quantile(allowed, request.allowed_quantile)), 6),
                allowed_mw_p25=round(float(np.quantile(allowed, 0.25)), 6),
                allowed_mw_p50=round(float(np.quantile(allowed, 0.50)), 6),
                allowed_mw_min=round(float(allowed.min()), 6),
                curtailed_mw_p90=round(float(np.quantile(curtailed, 0.90)), 6),
                dominant_incremental_constraint=_dominant_constraint(group),
            )
        )
    return ContractualEnvelopeResult(rows=tuple(rows))


def _direction(value: str) -> Direction:
    if value not in {"injection", "withdrawal"}:
        raise ValueError("direction must be 'injection' or 'withdrawal'")
    return value


def _season(month: int, direction: Direction) -> str:
    if direction == "injection":
        return "solar_mar_oct" if 3 <= month <= 10 else "non_solar_nov_feb"
    return "winter_nov_mar" if month in {11, 12, 1, 2, 3} else "non_winter_apr_oct"


def _time_block(hour: int) -> str:
    for start, end, label in TIME_BLOCKS:
        if start <= hour < end:
            return label
    raise ValueError("hour must be between 0 and 23")


def _datetime_from_timestamp(timestamp: str) -> datetime:
    try:
        return datetime.fromisoformat(str(timestamp))
    except ValueError:
        try:
            hour_index = int(timestamp)
        except (TypeError, ValueError):
            return datetime(2026, 1, 1)
        return datetime(2026, 1, 1) + timedelta(hours=hour_index)


def _dominant_constraint(records: list[EnvelopeRecordLike]) -> str:
    counts: dict[str, int] = {}
    for record in records:
        constraint = str(record.incremental_binding_constraint)
        if not constraint:
            continue
        counts[constraint] = counts.get(constraint, 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
