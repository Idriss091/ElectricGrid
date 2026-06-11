from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import pandas as pd


PORTFOLIO_REQUIRED_COLUMNS = (
    "client_site_id",
    "latitude",
    "longitude",
    "requested_mw",
    "storage_duration_hours",
)

PortfolioSource = str | Path | IO[str]


class PortfolioInputError(ValueError):
    """Raised when a client portfolio cannot be validated."""

    def __init__(self, errors: list[str] | tuple[str, ...]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class PortfolioSite:
    client_site_id: str
    latitude: float
    longitude: float
    requested_mw: float
    storage_duration_hours: float
    land_control_status: str | None = None
    target_connection_date: str | None = None
    max_connection_distance_km: float | None = None
    preferred_voltage_kv: float | None = None
    project_notes: str | None = None


def load_portfolio_sites(source: PortfolioSource) -> tuple[PortfolioSite, ...]:
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    missing = [column for column in PORTFOLIO_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise PortfolioInputError([f"missing required columns: {', '.join(missing)}"])
    if frame.empty:
        raise PortfolioInputError(["portfolio contains no sites"])

    errors: list[str] = []
    sites: list[PortfolioSite] = []
    seen_ids: set[str] = set()
    for row_number, row in enumerate(frame.to_dict(orient="records"), start=2):
        site_errors: list[str] = []
        site_id = str(row["client_site_id"]).strip()
        if not site_id:
            site_errors.append(f"row {row_number}: client_site_id is required")
        elif site_id in seen_ids:
            site_errors.append(
                f"row {row_number}: duplicate client_site_id '{site_id}'"
            )
        else:
            seen_ids.add(site_id)

        latitude = _parse_number(row["latitude"], "latitude", row_number, site_errors)
        longitude = _parse_number(row["longitude"], "longitude", row_number, site_errors)
        requested_mw = _parse_number(
            row["requested_mw"], "requested_mw", row_number, site_errors
        )
        duration = _parse_number(
            row["storage_duration_hours"],
            "storage_duration_hours",
            row_number,
            site_errors,
        )
        max_distance = _parse_optional_positive_number(
            row.get("max_connection_distance_km", ""),
            "max_connection_distance_km",
            row_number,
            site_errors,
        )
        preferred_voltage = _parse_optional_positive_number(
            row.get("preferred_voltage_kv", ""),
            "preferred_voltage_kv",
            row_number,
            site_errors,
        )

        if latitude is not None and not -90.0 <= latitude <= 90.0:
            site_errors.append(f"row {row_number}: latitude must be between -90 and 90")
        if longitude is not None and not -180.0 <= longitude <= 180.0:
            site_errors.append(
                f"row {row_number}: longitude must be between -180 and 180"
            )
        if requested_mw is not None and requested_mw <= 0.0:
            site_errors.append(f"row {row_number}: requested_mw must be greater than 0")
        if duration is not None and duration <= 0.0:
            site_errors.append(
                f"row {row_number}: storage_duration_hours must be greater than 0"
            )

        errors.extend(site_errors)
        if site_errors:
            continue

        assert latitude is not None
        assert longitude is not None
        assert requested_mw is not None
        assert duration is not None
        sites.append(
            PortfolioSite(
                client_site_id=site_id,
                latitude=latitude,
                longitude=longitude,
                requested_mw=requested_mw,
                storage_duration_hours=duration,
                land_control_status=_optional_text(row.get("land_control_status", "")),
                target_connection_date=_optional_text(
                    row.get("target_connection_date", "")
                ),
                max_connection_distance_km=max_distance,
                preferred_voltage_kv=preferred_voltage,
                project_notes=_optional_text(row.get("project_notes", "")),
            )
        )

    if errors:
        raise PortfolioInputError(errors)
    return tuple(sites)


def _parse_number(
    value: object,
    field: str,
    row_number: int,
    errors: list[str],
) -> float | None:
    try:
        result = float(str(value).strip())
    except ValueError:
        errors.append(f"row {row_number}: {field} must be a number")
        return None
    if not math.isfinite(result):
        errors.append(f"row {row_number}: {field} must be a finite number")
        return None
    return result


def _parse_optional_positive_number(
    value: object,
    field: str,
    row_number: int,
    errors: list[str],
) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    result = _parse_number(text, field, row_number, errors)
    if result is not None and result <= 0.0:
        errors.append(f"row {row_number}: {field} must be greater than 0")
    return result


def _optional_text(value: object) -> str | None:
    text = str(value).strip()
    return text or None
