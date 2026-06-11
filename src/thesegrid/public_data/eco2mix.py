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
        _text_series(frame["Date"]) + " " + _text_series(frame["Heures"]),
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )
    consumption = _numeric_series(frame["Consommation"])
    source_interval_minutes = _source_interval_minutes(timestamps)
    normalized = pd.DataFrame(
        {
            "timestamp": timestamps,
            "perimeter": _text_series(frame["Périmètre"]),
            "data_nature": _text_series(frame["Nature"]),
            "source_interval_minutes": source_interval_minutes,
            "consumption_mw": consumption,
            "consumption_measurement_available": consumption.notna().map(bool).astype(object),
            "solar_mw": _numeric_series(frame["Solaire"]),
            "wind_mw": _numeric_series(frame["Eolien"]),
            "battery_charge_mw": _numeric_series(frame[" Stockage batterie"]),
            "battery_discharge_mw": _numeric_series(frame["Déstockage batterie"]),
        }
    )
    normalized = normalized.dropna(subset=["timestamp"]).reset_index(drop=True)
    observed_count = int(
        normalized["consumption_measurement_available"].map(bool).sum()
    )
    interval_values = normalized["source_interval_minutes"].dropna()
    interval_minutes = (
        None if interval_values.empty else int(interval_values.mode().iloc[0])
    )
    return Eco2mixTable(
        frame=normalized,
        manifest=local_source_manifest(
            path,
            "eco2mix_annual",
            row_count=len(normalized),
            quality={
                "record_count": len(normalized),
                "source_interval_minutes": interval_minutes,
                "observed_consumption_count": observed_count,
                "missing_consumption_count": len(normalized) - observed_count,
            },
        ),
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
        manifest=local_source_manifest(
            path,
            "eco2mix_tempo",
            row_count=len(normalized),
            quality={"record_count": len(normalized)},
        ),
    )


def _read_tsv_with_fallback(path: Path) -> pd.DataFrame:
    try:
        return _read_tsv(path, encoding="latin1")
    except UnicodeDecodeError:
        return _read_tsv(path, encoding="utf-8")


def _read_tsv(path: Path, *, encoding: str) -> pd.DataFrame:
    columns = pd.read_csv(
        path,
        sep="\t",
        encoding=encoding,
        nrows=0,
    ).columns
    return pd.read_csv(
        path,
        sep="\t",
        encoding=encoding,
        usecols=range(len(columns)),
    )


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
    )


def _source_interval_minutes(timestamps: pd.Series) -> pd.Series:
    valid = timestamps.dropna().sort_values().drop_duplicates()
    differences = valid.diff().dropna().dt.total_seconds().div(60)
    positive_differences = differences[differences > 0]
    interval = (
        None
        if positive_differences.empty
        else int(positive_differences.mode().iloc[0])
    )
    return pd.Series(
        pd.array([interval] * len(timestamps), dtype="Int64"),
        index=timestamps.index,
    )
