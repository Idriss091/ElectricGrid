from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from thesegrid.public_data.sources import LocalSourceManifest, local_source_manifest


class OdreSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class OdreTable:
    frame: pd.DataFrame
    manifest: LocalSourceManifest


REGIONAL_CONSTRAINT_COLUMNS = (
    "Région",
    "Ouvrage",
    "Nom de l'ouvrage",
    "Puissance max de l'ouvrage",
    "Poste 1",
    "Pourcentage 1",
    "Occurrence",
    "Durée",
    "Pérennité",
    "Specificité",
)

STORAGE_ASSET_COLUMNS = (
    "region",
    "posteSource",
    "filiere",
    "typeStockage",
    "tensionRaccordement",
    "puisMaxInstallee",
    "puisMaxCharge",
    "puisMaxInstalleeDisCharge",
    "energieStockable",
    "nbInstallations",
)

REGIONAL_LOAD_COLUMNS = (
    "Date",
    "Code INSEE région",
    "Région",
    "Secteur activité",
    "Code tension raccordement",
    "Tension raccordement",
    "Nb points de soutirage",
    "Energie journalière (MWh)",
    "Qualité",
)


def read_regional_constraints(path: Path) -> OdreTable:
    frame = _read_csv(path)
    _require_columns(path, frame, REGIONAL_CONSTRAINT_COLUMNS)
    normalized = pd.DataFrame(
        {
            "region": _text_series(frame["Région"]),
            "work_id": _text_series(frame["Ouvrage"]),
            "work_name": _text_series(frame["Nom de l'ouvrage"]),
            "max_power_mw": _numeric_series(frame["Puissance max de l'ouvrage"]),
            "substation_1": _text_series(frame["Poste 1"]),
            "substation_1_percent": _numeric_series(frame["Pourcentage 1"]),
            "occurrence": _text_series(frame["Occurrence"]),
            "duration": _text_series(frame["Durée"]),
            "persistence": _text_series(frame["Pérennité"]),
            "specificity": _text_series(frame["Specificité"]),
        }
    )
    return OdreTable(
        frame=normalized,
        manifest=local_source_manifest(
            path,
            "odre_regional_constraints",
            row_count=len(normalized),
            quality={
                "row_count": len(normalized),
                "missing_max_power_count": int(normalized["max_power_mw"].isna().sum()),
            },
        ),
    )


def read_storage_assets(path: Path) -> OdreTable:
    frame = _read_csv(path)
    _require_columns(path, frame, STORAGE_ASSET_COLUMNS)
    storage_type = _text_series(frame["typeStockage"])
    normalized = pd.DataFrame(
        {
            "region": _text_series(frame["region"]),
            "source_substation": _text_series(frame["posteSource"]),
            "technology_family": _text_series(frame["filiere"]),
            "storage_type": storage_type,
            "connection_voltage": _text_series(frame["tensionRaccordement"]),
            "installed_kw": _numeric_series(frame["puisMaxInstallee"]),
            "charge_kw": _numeric_series(frame["puisMaxCharge"]),
            "discharge_kw": _numeric_series(frame["puisMaxInstalleeDisCharge"]),
            "stockable_kwh": _numeric_series(frame["energieStockable"]),
            "installation_count": _numeric_series(frame["nbInstallations"]),
        }
    )
    normalized["is_battery"] = (storage_type.str.upper() == "BATTE").map(bool).astype(object)
    return OdreTable(
        frame=normalized,
        manifest=local_source_manifest(
            path,
            "odre_storage_assets",
            row_count=len(normalized),
            quality={
                "row_count": len(normalized),
                "battery_row_count": int(normalized["is_battery"].map(bool).sum()),
            },
        ),
    )


def read_regional_load_profiles(path: Path) -> OdreTable:
    frame = _read_csv(path)
    _require_columns(path, frame, REGIONAL_LOAD_COLUMNS)
    half_hour_columns = tuple(
        column
        for column in frame.columns
        if isinstance(column, str) and len(column) == 5 and column[2] == "h"
    )
    half_hour_values = frame.loc[:, half_hour_columns].apply(_numeric_series)
    normalized = pd.DataFrame(
        {
            "date": _text_series(frame["Date"]),
            "region_code": _text_series(frame["Code INSEE région"]),
            "region": _text_series(frame["Région"]),
            "activity_sector": _text_series(frame["Secteur activité"]),
            "connection_voltage_code": _text_series(frame["Code tension raccordement"]),
            "connection_voltage": _text_series(frame["Tension raccordement"]),
            "withdrawal_point_count": _numeric_series(frame["Nb points de soutirage"]),
            "daily_energy_mwh": _numeric_series(frame["Energie journalière (MWh)"]),
            "quality": _text_series(frame["Qualité"]),
            "max_half_hour_mw": half_hour_values.max(axis=1),
        }
    )
    return OdreTable(
        frame=normalized,
        manifest=local_source_manifest(
            path,
            "odre_regional_load_profiles",
            row_count=len(normalized),
            quality={
                "row_count": len(normalized),
                "missing_daily_energy_count": int(
                    normalized["daily_energy_mwh"].isna().sum()
                ),
                "missing_half_hour_profile_count": int(
                    normalized["max_half_hour_mw"].isna().sum()
                ),
            },
        ),
    )


def _require_columns(path: Path, frame: pd.DataFrame, required_columns: tuple[str, ...]) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise OdreSchemaError(f"{path} missing columns: {', '.join(missing)}")


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")


def _text_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
