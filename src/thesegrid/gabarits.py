from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from thesegrid.models import Direction


class GabaritKind(str, Enum):
    FIRM_ONLY = "firm-only"
    RTE_INJECTION = "RTE injection-gabarit"
    RTE_WITHDRAWAL = "RTE withdrawal-gabarit"
    CUSTOM = "custom envelope"


def is_restricted(timestamp: datetime, direction: Direction, gabarit: GabaritKind) -> bool:
    """Return whether the CRE/RTE-inspired V1 gabarit forbids operation."""
    if gabarit == GabaritKind.RTE_INJECTION and direction == "injection":
        return 3 <= timestamp.month <= 10 and 10 <= timestamp.hour < 18
    if gabarit == GabaritKind.RTE_WITHDRAWAL and direction == "withdrawal":
        in_winter_months = timestamp.month in {11, 12, 1, 2, 3}
        in_morning = 7 <= timestamp.hour < 13
        in_evening = 17 <= timestamp.hour < 21
        return in_winter_months and (in_morning or in_evening)
    return False


def annual_timestamps(year: int) -> tuple[datetime, ...]:
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)
    timestamps: list[datetime] = []
    current = start
    while current < end:
        timestamps.append(current)
        current += timedelta(hours=1)
    return tuple(timestamps)


def restricted_hours(
    timestamps: tuple[datetime, ...],
    direction: Direction,
    gabarit: GabaritKind,
) -> int:
    return sum(1 for timestamp in timestamps if is_restricted(timestamp, direction, gabarit))
