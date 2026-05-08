from datetime import datetime

from thesegrid.gabarits import GabaritKind, annual_timestamps, is_restricted, restricted_hours


def test_rte_injection_gabarit_restricts_10_to_18_from_march_to_october():
    assert is_restricted(datetime(2026, 3, 1, 10), "injection", GabaritKind.RTE_INJECTION)
    assert is_restricted(datetime(2026, 10, 31, 17), "injection", GabaritKind.RTE_INJECTION)
    assert not is_restricted(datetime(2026, 3, 1, 9), "injection", GabaritKind.RTE_INJECTION)
    assert not is_restricted(datetime(2026, 3, 1, 18), "injection", GabaritKind.RTE_INJECTION)
    assert not is_restricted(datetime(2026, 11, 1, 12), "injection", GabaritKind.RTE_INJECTION)


def test_rte_withdrawal_gabarit_restricts_morning_and_evening_from_november_to_march():
    assert is_restricted(datetime(2026, 1, 15, 7), "withdrawal", GabaritKind.RTE_WITHDRAWAL)
    assert is_restricted(datetime(2026, 3, 31, 12), "withdrawal", GabaritKind.RTE_WITHDRAWAL)
    assert is_restricted(datetime(2026, 11, 1, 17), "withdrawal", GabaritKind.RTE_WITHDRAWAL)
    assert not is_restricted(datetime(2026, 1, 15, 13), "withdrawal", GabaritKind.RTE_WITHDRAWAL)
    assert not is_restricted(datetime(2026, 1, 15, 21), "withdrawal", GabaritKind.RTE_WITHDRAWAL)
    assert not is_restricted(datetime(2026, 4, 1, 8), "withdrawal", GabaritKind.RTE_WITHDRAWAL)


def test_annual_timestamps_are_hourly_and_restricted_hours_are_reproducible():
    timestamps = annual_timestamps(2026)

    assert len(timestamps) == 8760
    assert restricted_hours(timestamps, "injection", GabaritKind.RTE_INJECTION) == 1960
