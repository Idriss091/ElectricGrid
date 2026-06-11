from pathlib import Path
import math

import pandas as pd
import pytest

from thesegrid.public_data.odre import (
    OdreSchemaError,
    read_regional_load_profiles,
    read_regional_constraints,
    read_storage_assets,
)


def test_read_regional_constraints_handles_bom_and_required_columns(tmp_path: Path):
    path = tmp_path / "contraintes-region.csv"
    path.write_text(
        "\ufeffRégion,Ouvrage,Nom de l'ouvrage,Puissance max de l'ouvrage,"
        "Poste 1,Pourcentage 1,Occurrence,Durée,Pérennité,Specificité\n"
        "GRAND EST,ABC,LIAISON ABC,50.0,POSTE,-40.0,"
        "Forte : entre 75 et 150 fois par an,]2h-4h],ELEVEE,Contrainte en journée\n",
        encoding="utf-8",
    )

    result = read_regional_constraints(path)

    assert len(result.frame) == 1
    assert result.frame.loc[0, "region"] == "GRAND EST"
    assert result.frame.loc[0, "work_id"] == "ABC"
    assert result.frame.loc[0, "max_power_mw"] == 50.0
    assert result.frame.loc[0, "persistence"] == "ELEVEE"
    assert result.manifest.available is True
    assert result.manifest.row_count == 1
    assert result.manifest.transformation_version == "odre-regional-constraints-v1"


def test_read_regional_constraints_rejects_schema_drift(tmp_path: Path):
    path = tmp_path / "contraintes-region.csv"
    path.write_text("Région,Ouvrage\nGRAND EST,ABC\n", encoding="utf-8")

    with pytest.raises(OdreSchemaError, match="missing columns"):
        read_regional_constraints(path)


def test_read_storage_assets_normalizes_battery_rows(tmp_path: Path):
    path = tmp_path / "registre.csv"
    pd.DataFrame(
        [
            {
                "region": "Bretagne",
                "posteSource": "BRETA",
                "filiere": "Stockage non hydraulique",
                "typeStockage": "BATTE",
                "tensionRaccordement": "HTA",
                "puisMaxInstallee": "1200",
                "puisMaxCharge": "1000",
                "puisMaxInstalleeDisCharge": "1000",
                "energieStockable": "2400",
                "nbInstallations": "1",
            }
        ]
    ).to_csv(path, index=False)

    result = read_storage_assets(path)

    row = result.frame.iloc[0]
    assert row["region"] == "Bretagne"
    assert row["source_substation"] == "BRETA"
    assert row["is_battery"] is True
    assert row["installed_kw"] == 1200.0
    assert row["charge_kw"] == 1000.0
    assert row["discharge_kw"] == 1000.0
    assert row["stockable_kwh"] == 2400.0
    assert row["installation_count"] == 1.0
    assert result.manifest.row_count == 1


def test_read_regional_load_profiles_normalizes_wide_half_hourly_rows(tmp_path: Path):
    path = tmp_path / "soutirages-regionaux.csv"
    pd.DataFrame(
        [
            {
                "Date": "2026-06-09",
                "Code INSEE région": "76",
                "Région": "Occitanie",
                "Secteur activité": "Grande Industrie",
                "Code tension raccordement": "6",
                "Tension raccordement": "225 kV",
                "00h00": "10.5",
                "00h30": "11.5",
                "Nb points de soutirage": "2",
                "Energie journalière (MWh)": "22.0",
                "Qualité": "Provisoire",
            }
        ]
    ).to_csv(path, index=False)

    result = read_regional_load_profiles(path)

    row = result.frame.iloc[0]
    assert row["date"] == "2026-06-09"
    assert row["region"] == "Occitanie"
    assert row["connection_voltage"] == "225 kV"
    assert row["daily_energy_mwh"] == 22.0
    assert row["max_half_hour_mw"] == 11.5
    assert result.manifest.row_count == 1


def test_odre_readers_preserve_missing_numeric_measurements(tmp_path: Path):
    path = tmp_path / "soutirages-regionaux.csv"
    pd.DataFrame(
        [
            {
                "Date": "2026-06-09",
                "Code INSEE région": "76",
                "Région": "Occitanie",
                "Secteur activité": "Grande Industrie",
                "Code tension raccordement": "6",
                "Tension raccordement": "225 kV",
                "00h00": "",
                "00h30": "",
                "Nb points de soutirage": "",
                "Energie journalière (MWh)": "",
                "Qualité": "Provisoire",
            }
        ]
    ).to_csv(path, index=False)

    result = read_regional_load_profiles(path)

    assert math.isnan(result.frame.loc[0, "withdrawal_point_count"])
    assert math.isnan(result.frame.loc[0, "daily_energy_mwh"])
    assert math.isnan(result.frame.loc[0, "max_half_hour_mw"])
