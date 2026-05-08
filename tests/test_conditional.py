from datetime import datetime

from thesegrid.conditional import recommend_envelope


def test_recommend_envelope_finds_max_conditional_capacity_under_p90_tolerance():
    timestamps = tuple(datetime(2026, 1, day, 0) for day in range(1, 5))

    envelope = recommend_envelope(
        requested_mw=8.0,
        firm_injection_mw=3.0,
        firm_withdrawal_mw=3.0,
        timestamps=timestamps,
        p90_tolerance_mw=1.0,
        is_economically_viable=lambda _mw, _curtailment: True,
    )

    assert envelope.evaluated_mw == 8.0
    assert 3.95 <= envelope.conditional_capacity_mw <= 4.0
    assert envelope.conditional_capacity_mw < envelope.evaluated_mw


def test_recommend_envelope_caps_conditional_capacity_when_economics_turn_negative():
    timestamps = tuple(datetime(2026, 1, day, 0) for day in range(1, 5))

    envelope = recommend_envelope(
        requested_mw=8.0,
        firm_injection_mw=3.0,
        firm_withdrawal_mw=3.0,
        timestamps=timestamps,
        p90_tolerance_mw=5.0,
        is_economically_viable=lambda mw, _curtailment: mw <= 5.0,
    )

    assert 4.95 <= envelope.conditional_capacity_mw <= 5.0
    assert envelope.conditional_capacity_mw < envelope.evaluated_mw
