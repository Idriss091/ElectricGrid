from __future__ import annotations

import calendar

import pandas as pd

from thesegrid.gabarits import annual_timestamps


def to_hourly_profile(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or len(frame) in {8760, 8784}:
        return frame
    factor = _hourly_profile_aggregation_factor(len(frame))
    if factor is None:
        return frame
    grouped = frame.reset_index(drop=True).groupby(lambda idx: idx // factor).mean()
    grouped.index = range(len(grouped))
    return grouped


def profile_time_steps(
    profiles: dict[str, pd.DataFrame],
    start_hour: int = 0,
    duration_hours: int | None = None,
    sample_every_n_hours: int = 1,
    stratified_sample: bool = False,
    profile_year: int = 2026,
) -> tuple[int, ...]:
    lengths = [len(frame) for frame in profiles.values() if not frame.empty]
    if not lengths:
        return ()
    available = min(lengths)
    if start_hour >= available:
        return ()
    end = available if duration_hours is None else min(available, start_hour + duration_hours)
    if stratified_sample:
        stratified = stratified_time_steps(start_hour, end, profile_year=profile_year)
        if stratified:
            return stratified
    return tuple(range(start_hour, end, sample_every_n_hours))


def available_profile_hours(profiles: dict[str, pd.DataFrame]) -> int:
    lengths = [len(frame) for frame in profiles.values() if not frame.empty]
    return min(lengths) if lengths else 0


def time_step_weights(
    time_steps: tuple[int, ...],
    *,
    stratified_sample: bool,
    available_hours: int,
    profile_year: int = 2026,
) -> dict[int, float]:
    if not time_steps:
        return {}
    if not stratified_sample:
        return {time_step: 1.0 for time_step in time_steps}

    timestamps = annual_timestamps(profile_year)
    upper = min(available_hours, len(timestamps))
    if upper < 8760:
        return {time_step: 1.0 for time_step in time_steps}

    return {
        time_step: float(
            _days_in_month(profile_year, timestamps[time_step].month)
            * _time_block_width(timestamps[time_step].hour)
        )
        for time_step in time_steps
        if 0 <= time_step < len(timestamps)
    }


def timestamp_weights(
    time_steps: tuple[int, ...],
    weights_by_time_step: dict[int, float],
    profile_year: int = 2026,
) -> dict[str, float]:
    timestamps = timestamps_for_steps(time_steps, profile_year=profile_year)
    return {
        str(timestamp): weights_by_time_step.get(time_step, 1.0)
        for time_step, timestamp in zip(time_steps, timestamps, strict=True)
    }


def stratified_time_steps(
    start_hour: int,
    end_hour: int,
    *,
    profile_year: int = 2026,
) -> tuple[int, ...]:
    timestamps = annual_timestamps(profile_year)
    block_hours = (0, 7, 10, 13, 17, 18, 21)
    selected: list[int] = []
    seen: set[tuple[int, int]] = set()
    upper = min(end_hour, len(timestamps))
    for hour_index in range(start_hour, upper):
        timestamp = timestamps[hour_index]
        key = (timestamp.month, timestamp.hour)
        if timestamp.hour not in block_hours or key in seen:
            continue
        seen.add(key)
        selected.append(hour_index)
    return tuple(selected)


def timestamps_for_steps(
    time_steps: tuple[int, ...],
    *,
    profile_year: int = 2026,
) -> tuple[str | int, ...]:
    timestamps = annual_timestamps(profile_year)
    if all(0 <= time_step < len(timestamps) for time_step in time_steps):
        return tuple(timestamps[time_step].isoformat() for time_step in time_steps)
    return time_steps


def apply_profiles(net: object, profiles: dict[str, pd.DataFrame], time_step: int) -> None:
    _apply_profile(net, "load", "p_mw", profiles["load_p"], time_step)
    _apply_profile(net, "load", "q_mvar", profiles["load_q"], time_step)
    _apply_profile(net, "sgen", "p_mw", profiles["sgen_p"], time_step)
    _apply_profile(net, "sgen", "q_mvar", profiles["sgen_q"], time_step)
    _apply_profile(net, "gen", "p_mw", profiles["gen_p"], time_step)
    _apply_profile(net, "storage", "p_mw", profiles["storage_p"], time_step)


def _hourly_profile_aggregation_factor(profile_length: int) -> int | None:
    for annual_hours in (8784, 8760):
        if profile_length > annual_hours and profile_length % annual_hours == 0:
            return profile_length // annual_hours
    if profile_length % 4 == 0:
        return 4
    return None


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _time_block_width(hour: int) -> int:
    blocks = (
        (0, 7),
        (7, 10),
        (10, 13),
        (13, 17),
        (17, 18),
        (18, 21),
        (21, 24),
    )
    for start, end in blocks:
        if start <= hour < end:
            return end - start
    return 1


def _apply_profile(
    net: object,
    element: str,
    column: str,
    profile: pd.DataFrame,
    time_step: int,
) -> None:
    table = getattr(net, element, None)
    if table is None or profile.empty or column not in table:
        return
    values = profile.iloc[time_step]
    for element_id, value in values.items():
        if element_id in table.index:
            table.at[element_id, column] = float(value)
