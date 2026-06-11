import math
from pathlib import Path

import pytest

from thesegrid.public_data.eco2mix import (
    Eco2mixSchemaError,
    read_eco2mix_annual,
    read_tempo_days,
)


def test_read_eco2mix_annual_accepts_tsv_with_xls_extension(tmp_path: Path):
    path = tmp_path / "eCO2mix.xls"
    path.write_text(
        "Périmètre\tNature\tDate\tHeures\tConsommation\tSolaire\tEolien\t"
        " Stockage batterie\tDéstockage batterie\n"
        "France\tDonnées définitives\t2024-01-01\t00:00\t55000\t0\t15557\t0\t14976\n",
        encoding="latin1",
    )

    result = read_eco2mix_annual(path)

    row = result.frame.iloc[0]
    assert str(row["timestamp"]) == "2024-01-01 00:00:00"
    assert row["perimeter"] == "France"
    assert row["data_nature"] == "Données définitives"
    assert row["consumption_mw"] == 55000.0
    assert row["solar_mw"] == 0.0
    assert row["wind_mw"] == 15557.0
    assert row["battery_charge_mw"] == 0.0
    assert row["battery_discharge_mw"] == 14976.0
    assert row["consumption_measurement_available"] is True
    assert result.manifest.available is True
    assert result.manifest.row_count == 1
    assert result.manifest.transformation_version == "eco2mix-annual-v1"
    assert result.manifest.quality["record_count"] == 1
    assert result.manifest.quality["observed_consumption_count"] == 1
    assert result.manifest.quality["missing_consumption_count"] == 0


def test_read_eco2mix_annual_preserves_missing_quarter_hour_measurements(tmp_path: Path):
    path = tmp_path / "eCO2mix.xls"
    path.write_text(
        "Périmètre\tNature\tDate\tHeures\tConsommation\tSolaire\tEolien\t"
        " Stockage batterie\tDéstockage batterie\n"
        "France\tDonnées définitives\t2024-01-01\t00:00\t0\t0\t15557\t0\t0\n"
        "France\tDonnées définitives\t2024-01-01\t00:15\t\t\t\t\t\n",
        encoding="latin1",
    )

    result = read_eco2mix_annual(path)

    assert result.frame["source_interval_minutes"].tolist() == [15, 15]
    assert result.frame.loc[0, "consumption_mw"] == 0.0
    assert result.frame.loc[0, "consumption_measurement_available"] is True
    assert math.isnan(result.frame.loc[1, "consumption_mw"])
    assert result.frame.loc[1, "consumption_measurement_available"] is False
    assert math.isnan(result.frame.loc[1, "battery_charge_mw"])
    assert result.manifest.quality["source_interval_minutes"] == 15
    assert result.manifest.quality["observed_consumption_count"] == 1
    assert result.manifest.quality["missing_consumption_count"] == 1


def test_read_eco2mix_annual_ignores_undeclared_trailing_export_column(tmp_path: Path):
    path = tmp_path / "eCO2mix.xls"
    path.write_text(
        "Périmètre\tNature\tDate\tHeures\tConsommation\tSolaire\tEolien\t"
        " Stockage batterie\tDéstockage batterie\n"
        "France\tDonnées définitives\t2024-01-01\t00:00\t55239\t0\t15557\t0\t0\t\n",
        encoding="latin1",
    )

    result = read_eco2mix_annual(path)

    assert len(result.frame) == 1
    assert result.frame.loc[0, "perimeter"] == "France"
    assert result.frame.loc[0, "data_nature"] == "Données définitives"
    assert str(result.frame.loc[0, "timestamp"]) == "2024-01-01 00:00:00"
    assert result.frame.loc[0, "consumption_mw"] == 55239.0


def test_read_tempo_days_drops_rte_notice_line(tmp_path: Path):
    path = tmp_path / "tempo.xls"
    path.write_text(
        "Date\tType de jour TEMPO\n"
        "2024-09-01\tBLEU\n"
        "L'ensemble des informations disponibles sur éCO2mix sont fournies à titre informatif\t\n",
        encoding="utf-8",
    )

    result = read_tempo_days(path)

    assert len(result.frame) == 1
    assert str(result.frame.loc[0, "date"]) == "2024-09-01"
    assert result.frame.loc[0, "tempo_day_type"] == "BLEU"


def test_read_eco2mix_annual_rejects_missing_columns(tmp_path: Path):
    path = tmp_path / "bad.xls"
    path.write_text("Date\tConsommation\n2024-01-01\t1\n", encoding="utf-8")

    with pytest.raises(Eco2mixSchemaError, match="missing columns"):
        read_eco2mix_annual(path)
