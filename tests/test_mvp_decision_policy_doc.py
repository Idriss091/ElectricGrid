from pathlib import Path


def test_mvp_decision_policy_doc_defines_default_policy_and_verdicts():
    text = Path("docs/mvp-decision-policy.md").read_text(encoding="utf-8")

    assert "# MVP Decision Policy" in text
    assert "default investor-facing policy is `standard`" in text
    assert "`go`" in text
    assert "`go-with-conditions`" in text
    assert "`resize-recommended`" in text
    assert "`no-go`" in text
    assert "`investigate-only`" in text


def test_mvp_decision_policy_doc_exposes_standard_thresholds_and_status():
    text = Path("docs/mvp-decision-policy.md").read_text(encoding="utf-8")

    assert "p90_curtailment_ratio <= 10%" in text
    assert "curtailment_energy_ratio <= 1.0%" in text
    assert "max_event_hours <= 12" in text
    assert "max_event_mwh_per_mw <= 1.0" in text
    assert "not RTE, Enedis, CRE, or official operator thresholds" in text
    assert "must be calibrated" in text
