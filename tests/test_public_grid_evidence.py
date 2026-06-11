import pandas as pd

from thesegrid.public_data.evidence import build_public_grid_evidence


def test_build_public_grid_evidence_aggregates_region_and_battery_signals():
    constraints = pd.DataFrame(
        [
            {
                "region": "BRETAGNE",
                "occurrence": "Forte : entre 75 et 150 fois par an",
                "duration": "]2h-4h]",
                "persistence": "ELEVEE",
            },
            {
                "region": "BRETAGNE",
                "occurrence": "Faible : entre 5 et 25 fois par an",
                "duration": "]0h-2h]",
                "persistence": "MOYENNE",
            },
            {
                "region": "GRAND EST",
                "occurrence": "Très faible : jusqu'à 5 fois par an",
                "duration": "]0h-2h]",
                "persistence": "FAIBLE",
            },
        ]
    )
    storage = pd.DataFrame(
        [
            {
                "region": "BRETAGNE",
                "source_substation": "BRETA",
                "is_battery": True,
                "installed_kw": 1200.0,
                "stockable_kwh": 2400.0,
            },
            {
                "region": "BRETAGNE",
                "source_substation": "OTHER",
                "is_battery": True,
                "installed_kw": 300.0,
                "stockable_kwh": 600.0,
            },
        ]
    )
    regional_load = pd.DataFrame(
        [{"region": "BRETAGNE", "date": "2026-06-09"}]
    )
    eco2mix = pd.DataFrame(
        [{"timestamp": "2024-01-01 00:00:00"}, {"timestamp": "2024-01-01 00:15:00"}]
    )

    profiles = build_public_grid_evidence(
        site_candidates=[
            {"client_site_id": "S1", "region": "BRETAGNE", "odre_code": "BRETA"}
        ],
        regional_constraints=constraints,
        storage_assets=storage,
        regional_load_profiles=regional_load,
        eco2mix_annual=eco2mix,
    )

    profile = profiles[0]
    assert profile.client_site_id == "S1"
    assert profile.region == "BRETAGNE"
    assert profile.odre_code == "BRETA"
    assert profile.regional_constraint_count == 2
    assert profile.dominant_constraint_duration == "]2h-4h]"
    assert profile.high_persistence_constraint_count == 1
    assert profile.battery_storage_kw_region == 1500.0
    assert profile.battery_storage_kwh_region == 3000.0
    assert profile.battery_storage_kw_source_substation == 1200.0
    assert profile.latest_regional_load_date == "2026-06-09"
    assert profile.eco2mix_coverage_hours == 2
    assert profile.source_completeness_score == 1.0
    assert profile.missing_evidence == ()


def test_build_public_grid_evidence_records_missing_partial_sources():
    profiles = build_public_grid_evidence(
        site_candidates=[
            {"client_site_id": "S1", "region": "BRETAGNE", "odre_code": "BRETA"}
        ],
        regional_constraints=None,
        storage_assets=None,
        regional_load_profiles=None,
        eco2mix_annual=None,
    )

    profile = profiles[0]
    assert profile.regional_constraint_count == 0
    assert profile.battery_storage_kw_region == 0.0
    assert profile.latest_regional_load_date == ""
    assert profile.eco2mix_coverage_hours == 0
    assert profile.source_completeness_score == 0.0
    assert profile.missing_evidence == (
        "regional_constraints",
        "storage_assets",
        "regional_load_profiles",
        "eco2mix_annual",
    )
