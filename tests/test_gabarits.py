from datetime import datetime

from thesegrid.gabarits import (
    GabaritKind,
    annual_timestamps,
    gabarit_rule_rows,
    is_restricted,
    render_gabarit_rules_markdown,
    restricted_hours,
    rte_cre_inspired_v1_rules,
)


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


def test_rte_cre_inspired_v1_rules_are_explicit_business_objects():
    rules = rte_cre_inspired_v1_rules()

    injection = next(rule for rule in rules if rule.direction == "injection")
    assert injection.name == "rte_cre_inspired_v1_injection"
    assert injection.gabarit == GabaritKind.RTE_INJECTION
    assert injection.season == "solar_mar_oct"
    assert injection.time_block == "10-18"
    assert injection.months == (3, 4, 5, 6, 7, 8, 9, 10)
    assert injection.start_hour == 10
    assert injection.end_hour == 18
    assert injection.allowed_fraction == 0.0
    assert injection.allowed_mw is None
    assert injection.source_label == "RTE/CRE-inspired V1 storage gabarit"
    assert injection.valid_from == "2026-02-12"
    assert injection.prudence_level == "conservative_pre_feasibility"
    assert "not an official connection offer" in injection.notes


def test_gabarit_rule_rows_and_markdown_expose_french_connection_language():
    rules = rte_cre_inspired_v1_rules()

    rows = gabarit_rule_rows(rules)
    rendered = render_gabarit_rules_markdown(rules)

    assert rows[0]["source_label"] == "RTE/CRE-inspired V1 storage gabarit"
    assert rows[0]["valid_from"] == "2026-02-12"
    assert rows[0]["prudence_level"] == "conservative_pre_feasibility"
    assert "gabarit injection/soutirage" in rendered
    assert "PTF" in rendered
    assert "capacite d'accueil" in rendered
    assert "offre optimisee" in rendered


def test_gabarit_rule_rows_expose_regulatory_traceability_fields():
    rows = gabarit_rule_rows(rte_cre_inspired_v1_rules())

    row = rows[0]

    assert row["source_publication_date"] == "2026-02-20"
    assert row["effective_date"] == "2026-02-12"
    assert row["scope"] == "France BESS buyer-side pre-feasibility"
    assert row["hypothesis_status"] == "voltpath_proxy_not_official"
    assert row["source_url"] == (
        "https://www.services-rte.com/fr/actualites/"
        "offres-de-raccordement-a-gabarit-pour-les-installations-de-stockage.html"
    )
    assert "not a PTF" in row["limitation"]


def test_gabarit_markdown_includes_source_scope_hypothesis_and_limit():
    rendered = render_gabarit_rules_markdown(rte_cre_inspired_v1_rules())

    assert "source_publication_date" in rendered
    assert "effective_date" in rendered
    assert "hypothesis_status" in rendered
    assert "France BESS buyer-side pre-feasibility" in rendered
    assert "not a PTF" in rendered
