from thesegrid.decision_frontier import decision_frontier_rows, frontier_verdict


def test_frontier_v2_uses_project_normalized_risk_thresholds():
    rows = decision_frontier_rows(
        bus_id=21,
        bus_name="MV bus 21",
        requested_mw=5.0,
        qsts_p90_mw=0.4,
        weighted_curtailment_mwh=250.0,
        curtailment_energy_ratio=250.0 / (5.0 * 8760.0),
        max_event_hours=8,
        max_event_mwh=4.0,
        validation_level="qsts_full_year",
    )

    by_policy = {row.policy: row for row in rows}

    assert by_policy["strict"].frontier_verdict == "no-go"
    assert by_policy["standard"].frontier_verdict == "go-with-conditions"
    assert by_policy["standard"].p90_curtailment_ratio == 0.08
    assert by_policy["standard"].max_event_mwh_per_mw == 0.8


def test_aggressive_policy_is_investigate_only_above_flexible_risk():
    rows = decision_frontier_rows(
        bus_id=24,
        bus_name="MV bus 24",
        requested_mw=5.0,
        qsts_p90_mw=1.75,
        weighted_curtailment_mwh=1750.0,
        curtailment_energy_ratio=1750.0 / (5.0 * 8760.0),
        max_event_hours=72,
        max_event_mwh=20.0,
        validation_level="qsts_full_year",
    )

    by_policy = {row.policy: row for row in rows}

    assert by_policy["flexible"].frontier_verdict == "no-go"
    assert by_policy["aggressive"].frontier_verdict == "investigate-only"


def test_frontier_rejects_when_event_risk_exceeds_policy():
    policy = next(
        row.policy_definition
        for row in decision_frontier_rows(
            bus_id=2,
            bus_name="MV bus 2",
            requested_mw=5.0,
            qsts_p90_mw=0.0,
            weighted_curtailment_mwh=0.0,
            curtailment_energy_ratio=0.0,
            max_event_hours=0,
            max_event_mwh=0.0,
            validation_level="qsts_full_year",
        )
        if row.policy == "standard"
    )

    assert (
        frontier_verdict(
            p90_curtailment_ratio=0.05,
            curtailment_energy_ratio=0.005,
            max_event_hours=24,
            max_event_mwh_per_mw=0.5,
            policy=policy,
        )
        == "no-go"
    )
