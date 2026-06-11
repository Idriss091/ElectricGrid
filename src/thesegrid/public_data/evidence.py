from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class PublicGridEvidenceProfile:
    client_site_id: str
    region: str
    odre_code: str
    regional_constraint_count: int
    dominant_constraint_occurrence: str
    dominant_constraint_duration: str
    high_persistence_constraint_count: int
    battery_storage_kw_region: float
    battery_storage_kwh_region: float
    battery_storage_kw_source_substation: float
    latest_regional_load_date: str
    eco2mix_coverage_hours: float
    source_completeness_score: float
    missing_evidence: tuple[str, ...]
    eco2mix_record_count: int = 0
    eco2mix_source_interval_minutes: int | None = None
    eco2mix_observed_consumption_count: int = 0
    eco2mix_missing_consumption_count: int = 0


def build_public_grid_evidence(
    *,
    site_candidates: Sequence[Mapping[str, Any]],
    regional_constraints: pd.DataFrame | None,
    storage_assets: pd.DataFrame | None,
    regional_load_profiles: pd.DataFrame | None,
    eco2mix_annual: pd.DataFrame | None,
) -> tuple[PublicGridEvidenceProfile, ...]:
    missing_sources = _missing_sources(
        regional_constraints=regional_constraints,
        storage_assets=storage_assets,
        regional_load_profiles=regional_load_profiles,
        eco2mix_annual=eco2mix_annual,
    )
    source_completeness = round((4 - len(missing_sources)) / 4, 6)
    return tuple(
        _profile_for_candidate(
            candidate,
            regional_constraints=regional_constraints,
            storage_assets=storage_assets,
            regional_load_profiles=regional_load_profiles,
            eco2mix_annual=eco2mix_annual,
            source_completeness_score=source_completeness,
            missing_evidence=missing_sources,
        )
        for candidate in site_candidates
    )


def _profile_for_candidate(
    candidate: Mapping[str, Any],
    *,
    regional_constraints: pd.DataFrame | None,
    storage_assets: pd.DataFrame | None,
    regional_load_profiles: pd.DataFrame | None,
    eco2mix_annual: pd.DataFrame | None,
    source_completeness_score: float,
    missing_evidence: tuple[str, ...],
) -> PublicGridEvidenceProfile:
    client_site_id = str(candidate.get("client_site_id", ""))
    region = str(candidate.get("region", ""))
    odre_code = str(candidate.get("odre_code", ""))
    region_constraints = _rows_for_region(regional_constraints, region)
    region_storage = _battery_storage_for_region(storage_assets, region)
    substation_storage = _battery_storage_for_source_substation(storage_assets, odre_code)
    return PublicGridEvidenceProfile(
        client_site_id=client_site_id,
        region=region,
        odre_code=odre_code,
        regional_constraint_count=len(region_constraints),
        dominant_constraint_occurrence=_dominant_value(region_constraints, "occurrence"),
        dominant_constraint_duration=_dominant_value(region_constraints, "duration"),
        high_persistence_constraint_count=_high_persistence_count(region_constraints),
        battery_storage_kw_region=round(_sum_column(region_storage, "installed_kw"), 6),
        battery_storage_kwh_region=round(_sum_column(region_storage, "stockable_kwh"), 6),
        battery_storage_kw_source_substation=round(
            _sum_column(substation_storage, "installed_kw"),
            6,
        ),
        latest_regional_load_date=_latest_regional_load_date(regional_load_profiles, region),
        eco2mix_record_count=_eco2mix_record_count(eco2mix_annual),
        eco2mix_source_interval_minutes=_eco2mix_source_interval_minutes(
            eco2mix_annual
        ),
        eco2mix_observed_consumption_count=_eco2mix_observed_consumption_count(
            eco2mix_annual
        ),
        eco2mix_missing_consumption_count=_eco2mix_missing_consumption_count(
            eco2mix_annual
        ),
        eco2mix_coverage_hours=_eco2mix_coverage_hours(eco2mix_annual),
        source_completeness_score=source_completeness_score,
        missing_evidence=missing_evidence,
    )


def _missing_sources(
    *,
    regional_constraints: pd.DataFrame | None,
    storage_assets: pd.DataFrame | None,
    regional_load_profiles: pd.DataFrame | None,
    eco2mix_annual: pd.DataFrame | None,
) -> tuple[str, ...]:
    pairs = (
        ("regional_constraints", regional_constraints),
        ("storage_assets", storage_assets),
        ("regional_load_profiles", regional_load_profiles),
        ("eco2mix_annual", eco2mix_annual),
    )
    return tuple(name for name, frame in pairs if frame is None or frame.empty)


def _rows_for_region(frame: pd.DataFrame | None, region: str) -> pd.DataFrame:
    if frame is None or frame.empty or "region" not in frame:
        return pd.DataFrame()
    return frame[frame["region"].astype(str).str.upper() == region.upper()]


def _battery_storage_for_region(frame: pd.DataFrame | None, region: str) -> pd.DataFrame:
    rows = _rows_for_region(frame, region)
    if rows.empty or "is_battery" not in rows:
        return pd.DataFrame()
    return rows[rows["is_battery"].astype(bool)]


def _battery_storage_for_source_substation(
    frame: pd.DataFrame | None,
    source_substation: str,
) -> pd.DataFrame:
    if frame is None or frame.empty or "source_substation" not in frame or "is_battery" not in frame:
        return pd.DataFrame()
    rows = frame[
        frame["source_substation"].astype(str).str.upper() == source_substation.upper()
    ]
    return rows[rows["is_battery"].astype(bool)]


def _dominant_value(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame:
        return ""
    counts = frame[column].fillna("").astype(str).value_counts()
    if counts.empty:
        return ""
    return str(counts.index[0])


def _high_persistence_count(frame: pd.DataFrame) -> int:
    if frame.empty or "persistence" not in frame:
        return 0
    return int((frame["persistence"].fillna("").astype(str).str.upper() == "ELEVEE").sum())


def _sum_column(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).sum())


def _latest_regional_load_date(frame: pd.DataFrame | None, region: str) -> str:
    rows = _rows_for_region(frame, region)
    if rows.empty or "date" not in rows:
        return ""
    dates = pd.to_datetime(rows["date"], errors="coerce")
    if dates.dropna().empty:
        return ""
    return str(dates.max().date())


def _eco2mix_record_count(frame: pd.DataFrame | None) -> int:
    if frame is None or frame.empty:
        return 0
    return len(frame)


def _eco2mix_source_interval_minutes(frame: pd.DataFrame | None) -> int | None:
    if frame is None or frame.empty:
        return None
    if "source_interval_minutes" in frame:
        values = pd.to_numeric(
            frame["source_interval_minutes"],
            errors="coerce",
        ).dropna()
        if not values.empty:
            return int(values.mode().iloc[0])
    if "timestamp" not in frame:
        return None
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce").dropna()
    differences = (
        timestamps.sort_values()
        .drop_duplicates()
        .diff()
        .dropna()
        .dt.total_seconds()
        .div(60)
    )
    positive_differences = differences[differences > 0]
    if positive_differences.empty:
        return None
    return int(positive_differences.mode().iloc[0])


def _eco2mix_observed_consumption_count(frame: pd.DataFrame | None) -> int:
    if frame is None or frame.empty:
        return 0
    if "consumption_measurement_available" in frame:
        availability = frame["consumption_measurement_available"].map(
            lambda value: bool(value) if pd.notna(value) else False
        )
        return int(availability.sum())
    if "consumption_mw" in frame:
        return int(pd.to_numeric(frame["consumption_mw"], errors="coerce").notna().sum())
    return 0


def _eco2mix_missing_consumption_count(frame: pd.DataFrame | None) -> int:
    if frame is None or frame.empty:
        return 0
    return len(frame) - _eco2mix_observed_consumption_count(frame)


def _eco2mix_coverage_hours(frame: pd.DataFrame | None) -> float:
    interval = _eco2mix_source_interval_minutes(frame)
    if frame is None or frame.empty or interval is None:
        return 0.0
    return round(len(frame) * interval / 60.0, 6)
