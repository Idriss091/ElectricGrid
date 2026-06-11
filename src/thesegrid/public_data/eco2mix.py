from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from thesegrid.public_data.sources import LocalSourceManifest, local_source_manifest


class Eco2mixSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class Eco2mixTable:
    frame: pd.DataFrame
    manifest: LocalSourceManifest


ANNUAL_COLUMNS = (
    "Périmètre",
    "Nature",
    "Date",
    "Heures",
    "Consommation",
    "Solaire",
    "Eolien",
    " Stockage batterie",
    "Déstockage batterie",
)

TEMPO_COLUMNS = ("Date", "Type de jour TEMPO")


def read_eco2mix_annual(path: Path) -> Eco2mixTable:
    frame = _read_tsv_with_fallback(path)
    _require_columns(path, frame, ANNUAL_COLUMNS)
    timestamps = pd.to_datetime(
        _text_series(frame["Nature"]) + " " + _text_series(frame["Date"]),
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )
    normalized = pd.DataFrame(
        {
            "timestamp": timestamps,
            "consumption_mw": _numeric_series(frame["Heures"]),
            "solar_mw": _numeric_series(frame["Solaire"]),
            "wind_mw": _numeric_series(frame["Eolien"]),
            "battery_charge_mw": _numeric_series(frame[" Stockage batterie"]),
            "battery_discharge_mw": _numeric_series(frame["Déstockage batterie"]),
        }
    )
    normalized = normalized.dropna(subset=["timestamp"]).reset_index(drop=True)
    return Eco2mixTable(
        frame=normalized,
        manifest=local_source_manifest(path, "eco2mix_annual"),
    )


def read_tempo_days(path: Path) -> Eco2mixTable:
    frame = pd.read_csv(path, sep="\t", encoding="utf-8")
    _require_columns(path, frame, TEMPO_COLUMNS)
    dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="coerce")
    normalized = pd.DataFrame(
        {
            "date": dates.dt.date,
            "tempo_day_type": _text_series(frame["Type de jour TEMPO"]),
        }
    )
    normalized = normalized.dropna(subset=["date"]).reset_index(drop=True)
    return Eco2mixTable(
        frame=normalized,
        manifest=local_source_manifest(path, "eco2mix_tempo"),
    )


def _read_tsv_with_fallback(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, sep="\t", encoding="latin1")
    except UnicodeDecodeError:
        return pd.read_csv(path, sep="\t", encoding="utf-8")


def _require_columns(path: Path, frame: pd.DataFrame, required_columns: tuple[str, ...]) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise Eco2mixSchemaError(f"{path} missing columns: {', '.join(missing)}")


def _text_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    ).fillna(0.0)
