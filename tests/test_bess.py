import pytest

from thesegrid.bess import BessLiteAssumptions


def test_bess_lite_derives_nominal_and_usable_energy():
    bess = BessLiteAssumptions(
        power_mw=5.0,
        duration_hours=4.0,
        round_trip_efficiency=0.9,
        soc_min_fraction=0.1,
        soc_max_fraction=0.9,
    )

    assert bess.nominal_energy_mwh == 20.0
    assert bess.usable_soc_window == 0.8
    assert bess.usable_energy_mwh == 16.0
    assert bess.efficiency_adjusted_usable_energy_mwh == 14.4


def test_bess_lite_validates_physical_bounds():
    with pytest.raises(ValueError, match="power_mw"):
        BessLiteAssumptions(power_mw=0.0, duration_hours=4.0)

    with pytest.raises(ValueError, match="round_trip_efficiency"):
        BessLiteAssumptions(power_mw=5.0, duration_hours=4.0, round_trip_efficiency=1.2)

    with pytest.raises(ValueError, match="soc_min_fraction"):
        BessLiteAssumptions(power_mw=5.0, duration_hours=4.0, soc_min_fraction=-0.1)

    with pytest.raises(ValueError, match="soc_max_fraction"):
        BessLiteAssumptions(power_mw=5.0, duration_hours=4.0, soc_max_fraction=1.1)

    with pytest.raises(ValueError, match="soc_max_fraction must be greater"):
        BessLiteAssumptions(
            power_mw=5.0,
            duration_hours=4.0,
            soc_min_fraction=0.8,
            soc_max_fraction=0.8,
        )
