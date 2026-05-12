from types import SimpleNamespace

from thesegrid.contractual import synthesize_contractual_envelope


def test_contractual_envelope_groups_by_bus_direction_season_and_time_block():
    records = (
        _record("2026-03-01T10:00:00", 21, "bus-21", "injection", 5.0, 2.0, "bus[20] high"),
        _record("2026-04-01T12:00:00", 21, "bus-21", "injection", 3.0, 2.0, "bus[20] high"),
        _record("2026-11-01T08:00:00", 21, "bus-21", "withdrawal", 4.0, 1.0, "line[1] loading"),
        _record("2026-12-01T08:00:00", 21, "bus-21", "withdrawal", 2.0, 3.0, "line[1] loading"),
    )

    result = synthesize_contractual_envelope(records)

    assert len(result.rows) == 2
    injection = next(row for row in result.rows if row.direction == "injection")
    assert injection.bus_id == 21
    assert injection.season == "solar_mar_oct"
    assert injection.time_block == "10-13"
    assert injection.allowed_mw_p10 == 3.2
    assert injection.allowed_mw_p50 == 4.0
    assert injection.allowed_mw_min == 3.0
    assert injection.curtailed_mw_p90 == 2.0
    assert injection.dominant_incremental_constraint == "bus[20] high"

    withdrawal = next(row for row in result.rows if row.direction == "withdrawal")
    assert withdrawal.season == "winter_nov_mar"
    assert withdrawal.time_block == "07-10"
    assert withdrawal.allowed_mw_p10 == 2.2
    assert withdrawal.allowed_mw_p50 == 3.0
    assert withdrawal.allowed_mw_min == 2.0
    assert withdrawal.curtailed_mw_p90 == 2.8
    assert withdrawal.dominant_incremental_constraint == "line[1] loading"


def test_contractual_envelope_keeps_injection_and_withdrawal_separate():
    records = (
        _record("2026-01-01T01:00:00", 2, "bus-2", "injection", 5.0, 0.0, ""),
        _record("2026-01-01T01:00:00", 2, "bus-2", "withdrawal", 1.0, 4.0, "trafo[0] loading"),
    )

    result = synthesize_contractual_envelope(records)

    assert [(row.direction, row.season, row.time_block) for row in result.rows] == [
        ("injection", "non_solar_nov_feb", "00-07"),
        ("withdrawal", "winter_nov_mar", "00-07"),
    ]


def _record(timestamp, bus_id, bus_name, direction, allowed_mw, curtailed_mw, constraint):
    return SimpleNamespace(
        timestamp=timestamp,
        bus_id=bus_id,
        bus_name=bus_name,
        direction=direction,
        requested_mw=5.0,
        allowed_mw=allowed_mw,
        curtailed_mw=curtailed_mw,
        incremental_binding_constraint=constraint,
        qsts_verdict_context="go-with-conditions",
    )
