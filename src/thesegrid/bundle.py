from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from thesegrid.decision_frontier import DECISION_FRONTIER_POLICIES, frontier_verdict
from thesegrid.economic_scenarios import (
    EconomicScenarioAssumptions,
    compare_economic_scenarios,
    economic_scenario_rows,
    render_economic_scenarios_markdown,
)
from thesegrid.gabarits import (
    gabarit_rule_rows,
    render_gabarit_rules_markdown,
    rte_cre_inspired_v1_rules,
)


@dataclass(frozen=True)
class BundleReportPaths:
    html_path: Path
    scorecard_path: Path
    campaign_guide_path: Path
    economic_csv_path: Path
    economic_markdown_path: Path
    gabarit_csv_path: Path
    gabarit_markdown_path: Path
    resize_markdown_path: Path


@dataclass(frozen=True)
class BundleContext:
    network_code: str
    requested_mw: float
    asset: str
    data_source_type: str
    evidence_level: str
    decision_confidence: str
    recommended_next_action: str


def write_bundle_report(bundle_dir: Path) -> BundleReportPaths:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    html_path = bundle_dir / "investor_report.html"
    scorecard_path = bundle_dir / "scorecard.md"
    campaign_guide_path = bundle_dir / "next_calibration_campaign.md"
    economic_csv_path = bundle_dir / "economic_scenarios.csv"
    economic_markdown_path = bundle_dir / "economic_scenarios.md"
    gabarit_csv_path = bundle_dir / "gabarit_assumptions.csv"
    gabarit_markdown_path = bundle_dir / "gabarit_assumptions.md"
    resize_markdown_path = bundle_dir / "resize_recommendation.md"
    economic_scenarios = _economic_scenarios(bundle_dir)
    _write_csv(economic_csv_path, economic_scenario_rows(economic_scenarios))
    economic_markdown_path.write_text(
        render_economic_scenarios_markdown(economic_scenarios, EconomicScenarioAssumptions()),
        encoding="utf-8",
    )
    gabarit_rules = rte_cre_inspired_v1_rules()
    _write_csv(gabarit_csv_path, list(gabarit_rule_rows(gabarit_rules)))
    gabarit_markdown_path.write_text(
        render_gabarit_rules_markdown(gabarit_rules),
        encoding="utf-8",
    )
    resize_markdown_path.write_text(
        render_resize_recommendation_markdown(bundle_dir),
        encoding="utf-8",
    )
    html_path.write_text(render_bundle_html(bundle_dir), encoding="utf-8")
    scorecard_path.write_text(render_bundle_scorecard(bundle_dir), encoding="utf-8")
    campaign_guide_path.write_text(render_next_calibration_campaign(bundle_dir), encoding="utf-8")
    return BundleReportPaths(
        html_path=html_path,
        scorecard_path=scorecard_path,
        campaign_guide_path=campaign_guide_path,
        economic_csv_path=economic_csv_path,
        economic_markdown_path=economic_markdown_path,
        gabarit_csv_path=gabarit_csv_path,
        gabarit_markdown_path=gabarit_markdown_path,
        resize_markdown_path=resize_markdown_path,
    )


def render_bundle_scorecard(bundle_dir: Path) -> str:
    validation = _read_csv(bundle_dir / "validation_matrix.csv")
    resize = _read_csv(bundle_dir / "resize_results.csv")
    qsts = _read_csv(bundle_dir / "qsts_results.csv")
    performance = _read_json(bundle_dir / "qsts_performance.json")

    total_buses = len(validation)
    full_year_buses = sum(1 for row in validation if row.get("qsts_full_year_verdict"))
    false_positive_stratified = sum(
        1 for row in validation if row.get("calibration_status") == "false_positive_stratified"
    )
    resize_recommendations = sum(
        1 for row in resize if row.get("product_decision") == "resize-recommended"
    )
    no_go_full_year = sum(1 for row in validation if _primary_verdict(row) == "no-go")
    legacy_no_go_full_year = sum(
        1 for row in validation if row.get("legacy_qsts_full_year_verdict", row.get("qsts_full_year_verdict")) == "no-go"
    )
    readiness = _readiness(total_buses, full_year_buses, resize_recommendations)
    runtime_seconds = float(performance.get("total_full_year_runtime_seconds", 0.0))
    resize_summary = _best_resize_scorecard_line(resize)

    return f"""# MVP Evidence Scorecard

- readiness: {readiness}
- full_year_coverage: {full_year_buses}/{total_buses} buses
- selected_policy_no_go: {no_go_full_year}
- legacy_qsts_full_year_no_go: {legacy_no_go_full_year}
- false_positive_stratified: {false_positive_stratified}
- resize_recommendations: {resize_recommendations}
- best_resize_recommendation: {resize_summary}
- decision_policy: docs/mvp-decision-policy.md
- full_year_runtime_minutes: {runtime_seconds / 60:.2f}
- qsts_result_rows: {len(qsts)}

## Interpretation

This bundle is demo-ready when all evaluated buses have full-year QSTS evidence and at
least one rejected site has an actionable resize recommendation. It remains a
buyer-side pre-feasibility aid and does not replace an official grid-connection study.
"""


def render_resize_recommendation_markdown(bundle_dir: Path) -> str:
    resize = _read_csv(bundle_dir / "resize_results.csv")
    best = _best_resize_row(resize)
    if best is None:
        return """# Resize Recommendation

No resize recommendation is available.
"""

    original_mw = _float_or_none(best.get("original_requested_mw")) or 0.0
    recommended_mw = _float_or_none(best.get("requested_mw")) or 0.0
    delta_mw = recommended_mw - original_mw
    bus_id = _resize_bus_id(best)
    driver = best.get("verdict_driver", "")
    constraint = best.get("main_recurring_constraint", "")
    return f"""# Resize Recommendation

Original request: {original_mw:.3f} MW
Recommended size: {recommended_mw:.3f} MW
Delta: {delta_mw:.3f} MW
Bus: {bus_id}
Decision: {best.get("product_decision", "")}
Policy verdict: {_selected_policy_verdict(best)}
Main driver: {driver}
Dominant constraint: {constraint}

Reason: the original requested MW fails the selected policy; the recommended size is
the largest tested acceptable resize in `resize_results.csv`.
"""


def render_bundle_html(bundle_dir: Path) -> str:
    validation = _read_csv(bundle_dir / "validation_matrix.csv")
    resize = _read_csv(bundle_dir / "resize_results.csv")
    qsts = _read_csv(bundle_dir / "qsts_results.csv")
    qsts_risk = _read_csv(bundle_dir / "qsts_risk_summary.csv")
    screening = _read_csv(bundle_dir / "screening.csv")
    stratified_candidates = _read_csv(bundle_dir / "stratified_candidate_selection.csv")
    sensitivity = _read_csv(bundle_dir / "sensitivity_results.csv")
    full_year_conditional = _read_csv(bundle_dir / "full_year_conditional_results.csv")
    full_year_additional = _read_csv(bundle_dir / "full_year_additional_results.csv")
    full_year_checks = full_year_additional or full_year_conditional
    decision_frontier = _read_csv(bundle_dir / "decision_frontier.csv")
    full_year_candidates = _read_csv(bundle_dir / "full_year_candidate_selection.csv")
    economic_scenarios = _economic_scenarios(bundle_dir)
    gabarit_rows = _gabarit_assumption_rows(bundle_dir)
    scorecard = render_bundle_scorecard(bundle_dir)
    metrics = _bundle_metrics(validation, resize, qsts, bundle_dir)
    context = _bundle_context(bundle_dir)
    recommended_resize = _render_recommended_resize(resize)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VoltPath BESS Investor Evidence</title>
  <style>
    :root {{
      --ink: #17202a;
      --muted: #52616f;
      --line: #c7d2da;
      --paper: #f7f8f4;
      --panel: #ffffff;
      --amber: #b7791f;
      --red: #9f1d20;
      --green: #147d64;
      --blue: #1f5f8b;
      --teal: #0f766e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "IBM Plex Sans", "Source Sans 3", "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 34px 28px 56px; }}
    .hero {{
      border-top: 6px solid var(--ink);
      display: grid;
      grid-template-columns: 1.35fr .65fr;
      gap: 28px;
      padding: 28px 0 18px;
    }}
    h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: 46px; line-height: 1.02; margin: 0 0 12px; letter-spacing: 0; }}
    h2 {{ font-size: 22px; margin: 34px 0 12px; }}
    h3 {{ font-size: 15px; margin: 0 0 8px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }}
    p {{ margin: 0 0 12px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 26px; font-size: 13px; background: var(--panel); }}
    th, td {{ border: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #e9eef0; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    a {{ color: var(--blue); font-weight: 700; }}
    .notice {{ background: #fff6db; border-left: 5px solid var(--amber); padding: 12px 16px; margin: 16px 0; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); padding: 18px; }}
    .decision-callout {{ border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: 22px 0; margin: 18px 0 6px; display: grid; grid-template-columns: .9fr 1.1fr; gap: 24px; align-items: start; }}
    .decision-callout .eyebrow {{ color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }}
    .decision-callout h2 {{ font-size: 32px; margin: 0 0 8px; }}
    .decision-callout strong {{ color: var(--teal); }}
    .decision-list {{ margin: 0; padding-left: 18px; }}
    .decision-list li {{ margin: 0 0 8px; }}
    .funnel {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 16px 0 8px; }}
    .funnel-stage {{ background: var(--panel); border: 1px solid var(--line); padding: 14px; position: relative; min-height: 118px; }}
    .funnel-stage::after {{ content: ""; position: absolute; top: 50%; right: -9px; width: 0; height: 0; border-top: 9px solid transparent; border-bottom: 9px solid transparent; border-left: 9px solid var(--line); transform: translateY(-50%); }}
    .funnel-stage:last-child::after {{ display: none; }}
    .funnel-stage strong {{ display: block; font-size: 26px; line-height: 1; margin: 6px 0 6px; }}
    .funnel-stage span {{ color: var(--muted); font-size: 13px; }}
    .metric-strip {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }}
    .metric {{ background: var(--panel); border: 1px solid var(--line); padding: 12px; }}
    .metric strong {{ display: block; font-size: 20px; margin-bottom: 4px; }}
    .metric span {{ color: var(--muted); font-size: 12px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 20px 0; }}
    .kpi {{ background: var(--panel); border: 1px solid var(--line); padding: 14px; min-height: 92px; }}
    .kpi strong {{ display: block; font-size: 26px; line-height: 1; margin-bottom: 8px; }}
    .kpi span {{ color: var(--muted); font-size: 13px; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 3px 9px; font-size: 12px; font-weight: 800; letter-spacing: .02em; }}
    .badge-no-go {{ background: #fde2e2; color: var(--red); }}
    .badge-resize {{ background: #dff7ef; color: var(--green); }}
    .badge-evidence {{ background: #dceeff; color: var(--blue); }}
    .artifact-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .artifact-grid a {{ background: var(--panel); border: 1px solid var(--line); padding: 12px; text-decoration: none; }}
    .scorecard {{ background: #edf2f4; border: 1px solid var(--line); padding: 16px; white-space: pre-wrap; overflow-x: auto; }}
    details {{ border-top: 1px solid var(--line); padding: 14px 0; }}
    summary {{ cursor: pointer; font-weight: 800; }}
    @media (max-width: 820px) {{
      main {{ padding: 22px 16px 42px; }}
      .hero, .decision-callout, .funnel, .metric-strip, .kpis, .artifact-grid {{ grid-template-columns: 1fr; }}
      .funnel-stage::after {{ display: none; }}
      h1 {{ font-size: 34px; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div>
        <h1>VoltPath BESS Investor Evidence</h1>
        <p>Flexible-connection pre-feasibility for a {_format_mw_header(context.requested_mw)} {html.escape(context.asset.upper())} candidate set on network <strong>{html.escape(context.network_code)}</strong>.</p>
      </div>
      <aside class="panel">
        <h3>Investment Decision</h3>
        <p>{_decision_sentence(metrics, context.requested_mw)}</p>
        <p>{_badge("no-go", "badge-no-go")} {_badge("resize-recommended", "badge-resize")} {_badge("full-year evidence", "badge-evidence")}</p>
      </aside>
    </section>

    {_render_investor_recommendation(qsts, qsts_risk, context)}

    <section>
      <h2>Site Selection Funnel</h2>
      <p>The report narrows a large bus list into investable evidence: fast screening first, stratified QSTS for the shortlist, then full-year QSTS only on the finalists.</p>
      {_render_site_selection_funnel(screening, stratified_candidates, full_year_candidates, qsts, metrics)}
    </section>

    <section>
      <h2>Candidate Ranking</h2>
      <p>Full-year QSTS is the decision evidence. The ranking prefers acceptable decisions, then lower annual curtailed energy, then lower P90 curtailment.</p>
      {_render_candidate_ranking(qsts, qsts_risk)}
    </section>

    <section>
      <h2>Why Conditions?</h2>
      {_render_conditions_explainer(qsts, qsts_risk, context)}
    </section>

    <section>
      <h2>Executive Summary</h2>
      <div class="kpis">
        <div class="kpi"><strong>{metrics['full_year_coverage']}</strong><span>full-year coverage</span></div>
        <div class="kpi"><strong>{metrics['full_year_no_go']}</strong><span>full-year no-go buses</span></div>
        <div class="kpi"><strong>{metrics['false_positive_stratified']}</strong><span>stratified false positives</span></div>
        <div class="kpi"><strong>{metrics['resize_recommendations']}</strong><span>resize recommendations</span></div>
      </div>
    </section>

    {_render_resize_section(recommended_resize)}

    <section>
      <h2>Decision Summary</h2>
      {_html_table(_decision_summary_rows(validation, qsts))}
    </section>

    <section>
      <h2>Proxy Economics</h2>
      <p class="notice">This is proxy economics, not bankable revenue modelling. Values are scenario-comparison aids only.</p>
      {_html_table(_stringify_rows(economic_scenario_rows(economic_scenarios)))}
    </section>

    <section>
      <h2>Technical Appendix</h2>
      <details open>
        <summary>Regulatory Assumption Traceability</summary>
        <p class="notice">The RTE/CRE-inspired gabarit preset is a VoltPath pre-feasibility proxy. Each rule is labelled with source timing, scope, hypothesis status, and limitation to avoid implying an official PTF or operator offer.</p>
        {_html_table(gabarit_rows)}
      </details>
      <details>
        <summary>Scorecard</summary>
        <div class="scorecard">{html.escape(scorecard)}</div>
      </details>
      <details>
        <summary>Evidence Tables</summary>
        <h3>Validation Matrix</h3>
        {_html_table(validation)}
        <h3>Full-Year QSTS Results</h3>
        {_html_table(qsts)}
        <h3>Resize Evidence</h3>
        {_html_table(resize)}
      </details>
      <details>
        <summary>Decision Matrix</summary>
        <p class="notice">This matrix is stratified QSTS evidence when generated from the bus-by-MW sweep. Full-year QSTS is required before using any go verdict as investor-grade evidence.</p>
        {_render_decision_matrix(sensitivity)}
        <h3>Recommended MW by Bus</h3>
        {_render_recommended_mw_by_bus(sensitivity)}
        <h3>Full-Year Conditional Checks</h3>
        {_render_full_year_conditional_checks(full_year_checks)}
        <h3>Decision Frontier</h3>
        {_render_decision_frontier(decision_frontier or _frontier_rows(qsts, full_year_checks))}
        <h3>Next Full-Year Candidates</h3>
        {_render_next_full_year_candidates(full_year_candidates)}
      </details>
    </section>

    <section>
      <h2>Bundle Artifacts</h2>
      <div class="artifact-grid">
        {_artifact_link("validation_matrix.csv")}
        {_artifact_link("resize_results.csv")}
        {_artifact_link("economic_scenarios.csv")}
        {_artifact_link("gabarit_assumptions.csv")}
        {_artifact_link("gabarit_assumptions.md")}
        {_artifact_link("qsts_economics.csv")}
        {_artifact_link("decision_frontier.csv")}
        {_artifact_link("qsts_results.csv")}
        {_artifact_link("qsts_risk_summary.csv")}
        {_artifact_link("contractual_envelope.csv")}
        {_artifact_link("run_manifest.json")}
      </div>
    </section>

    <section>
      <h2>Important Notice</h2>
      <p class="notice">This is a buyer-side pre-feasibility aid, not an official grid-connection study, PTF, or RTE/Enedis offer.</p>
    </section>
  </main>
</body>
</html>
"""


def _render_investor_recommendation(
    qsts: list[dict[str, str]],
    qsts_risk: list[dict[str, str]],
    context: BundleContext,
) -> str:
    best = _best_qsts_candidate(qsts)
    if best is None:
        return """
    <section class="decision-callout">
      <div>
        <div class="eyebrow">Recommendation</div>
        <h2>Run full-year QSTS</h2>
        <p>No full-year finalist is available in this bundle yet.</p>
      </div>
      <div><p>Use this report after the shortlist has at least one full-year QSTS row.</p></div>
    </section>
"""

    risk = _risk_for_bus(best, qsts_risk)
    decision = _decision_label(_qsts_decision(best))
    bus_label = _bus_label(best)
    annual_mwh = _risk_float(risk, best, "expected_curtailment_mwh")
    p90_mw = _risk_float(risk, best, "curtailment_p90_mw", "p90_curtailment_mw")
    event_hours = _risk_text(risk, best, "max_event_hours")
    event_mwh = _risk_float(risk, best, "max_event_mwh")
    condition = _condition_instruction(risk.get("dominant_constraint") or best.get("main_recurring_constraint", ""))
    return f"""
    <section class="decision-callout">
      <div>
        <div class="eyebrow">Recommendation</div>
        <h2>{html.escape(decision)}</h2>
        <p><strong>Recommended candidate:</strong> {html.escape(bus_label)} at {_format_mw_header(context.requested_mw)}.</p>
        <p>{html.escape(condition)}</p>
      </div>
      <div>
        <ul class="decision-list">
          <li>Full-year QSTS evidence is available for this candidate.</li>
          <li>Expected curtailed energy is {_format_optional_mwh(annual_mwh)} over the year.</li>
          <li>P90 curtailment is {_format_optional_mw(p90_mw)}, so most operating hours are unconstrained.</li>
          <li>The worst detected event lasts {_format_optional_hours(event_hours)} and represents {_format_optional_mwh(event_mwh)}.</li>
        </ul>
      </div>
    </section>
"""


def _render_site_selection_funnel(
    screening: list[dict[str, str]],
    stratified_candidates: list[dict[str, str]],
    full_year_candidates: list[dict[str, str]],
    qsts: list[dict[str, str]],
    metrics: dict[str, object],
) -> str:
    full_year_rows = [row for row in qsts if row.get("validation_level") in {"", "qsts_full_year"}]
    acceptable = sum(1 for row in full_year_rows if _qsts_decision(row) in {"go", "go-with-conditions"})
    stages = [
        {
            "title": "Screening",
            "value": _count_or_dash(screening),
            "text": "Fast static capacity pass across candidate buses.",
        },
        {
            "title": "Stratified QSTS",
            "value": _count_or_dash(stratified_candidates),
            "text": "Representative days narrow the shortlist before expensive full-year runs.",
        },
        {
            "title": "Full-year QSTS",
            "value": str(len(full_year_rows)) if full_year_rows else str(metrics["full_year_coverage"]),
            "text": "Hourly validation over the full simulated year for the finalists.",
        },
        {
            "title": "Decision",
            "value": str(acceptable),
            "text": "Candidates with go or go-with-conditions under the selected policy.",
        },
    ]
    cards = "".join(
        f"""
        <div class="funnel-stage">
          <h3>{html.escape(stage["title"])}</h3>
          <strong>{html.escape(stage["value"])}</strong>
          <span>{html.escape(stage["text"])}</span>
        </div>
"""
        for stage in stages
    )
    return f'<div class="funnel">{cards}</div>'


def _render_candidate_ranking(
    qsts: list[dict[str, str]],
    qsts_risk: list[dict[str, str]],
) -> str:
    if not qsts:
        return "<p>No full-year QSTS candidate rows are available yet.</p>"
    rows: list[dict[str, str]] = []
    for index, row in enumerate(_sorted_qsts_candidates(qsts), start=1):
        risk = _risk_for_bus(row, qsts_risk)
        annual_mwh = _risk_float(risk, row, "expected_curtailment_mwh")
        p90_mw = _risk_float(risk, row, "curtailment_p90_mw", "p90_curtailment_mw")
        hours = _risk_text(risk, row, "curtailment_hours", "violation_hours")
        event_hours = _risk_text(risk, row, "max_event_hours")
        event_mwh = _risk_float(risk, row, "max_event_mwh")
        rows.append(
            {
                "rank": str(index),
                "bus": _bus_label(row),
                "decision": _qsts_decision(row),
                "annual_curtailed_mwh": _format_optional_number(annual_mwh, "MWh"),
                "constrained_hours": _format_optional_hours(hours),
                "p90_curtailment_mw": _format_optional_number(p90_mw, "MW"),
                "worst_event": _format_event(event_hours, event_mwh),
                "condition": _condition_instruction(
                    risk.get("dominant_constraint") or row.get("main_recurring_constraint", "")
                ),
            }
        )
    return _html_table(rows)


def _render_conditions_explainer(
    qsts: list[dict[str, str]],
    qsts_risk: list[dict[str, str]],
    context: BundleContext,
) -> str:
    best = _best_qsts_candidate(qsts)
    if best is None:
        return "<p>No full-year QSTS row is available to explain conditions yet.</p>"
    risk = _risk_for_bus(best, qsts_risk)
    annual_mwh = _risk_float(risk, best, "expected_curtailment_mwh")
    p90_mw = _risk_float(risk, best, "curtailment_p90_mw", "p90_curtailment_mw")
    hours = _risk_text(risk, best, "curtailment_hours", "violation_hours")
    event_hours = _risk_text(risk, best, "max_event_hours")
    event_mwh = _risk_float(risk, best, "max_event_mwh")
    condition = _condition_instruction(risk.get("dominant_constraint") or best.get("main_recurring_constraint", ""))
    return f"""
      <p>The selected candidate is not labelled plain go because the network is not firm for every simulated hour at {_format_mw_header(context.requested_mw)}. It is labelled <strong>go-with-conditions</strong> because the full-year risk is limited and can be translated into a flexible operating envelope.</p>
      <div class="metric-strip">
        <div class="metric"><strong>{_format_optional_hours(hours)}</strong><span>constrained hours in the year</span></div>
        <div class="metric"><strong>{_format_optional_mwh(annual_mwh)}</strong><span>expected curtailed energy</span></div>
        <div class="metric"><strong>{_format_event(event_hours, event_mwh)}</strong><span>worst single event</span></div>
        <div class="metric"><strong>{_format_optional_mw(p90_mw)}</strong><span>P90 curtailment</span></div>
      </div>
      <p><strong>Operational condition:</strong> {html.escape(condition)}</p>
      <p>For a BESS developer, this is the value proposition: avoid rejecting a mostly workable site, but price and contract the rare constrained hours instead of pretending the connection is fully firm.</p>
"""


def _render_resize_section(rendered_resize: str) -> str:
    if "No resize recommendation is available." in rendered_resize:
        return ""
    return f"""
    <section>
      <h2>Recommended Resize</h2>
      {rendered_resize}
    </section>
"""


def render_next_calibration_campaign(bundle_dir: Path) -> str:
    return """# Next Calibration Campaign

## Goal

Expand the current BESS evidence beyond the first investor bundle while keeping the V1
focused on BESS France and buyer-side pre-feasibility.

## Recommended Matrix

- Networks: run the four core SimBench MV archetypes:
  `1-MV-rural--0-sw`, `1-MV-semiurb--0-sw`, `1-MV-urban--0-sw`, and
  `1-MV-comm--0-sw`.
- Buses: screen all eligible MV buses, run stratified QSTS on a balanced shortlist, then
  run full-year QSTS on one best candidate and one risk candidate per network.
- Requested MW value: start with 5 MW.
- Decision policy: use the `standard` policy frontier. For 5 MW legacy CLI tolerances,
  pass P90 = 0.5 MW and expected curtailed energy = 438 MWh.
- Evidence levels: screening for all candidates, short QSTS for smoke validation,
  stratified QSTS for shortlist comparison, and full-year QSTS only for final
  candidates or calibration controls.

## Execution Rule

Run full-year QSTS by bus as the parallelization unit. Keep each scenario output under
`results/`, then regenerate the validation matrix and investor bundle.

## Stop Criteria

Stop expanding scenarios once the matrix has enough evidence to estimate false-positive
rates for screening and stratified QSTS on at least two networks.
"""


def _readiness(total_buses: int, full_year_buses: int, resize_recommendations: int) -> str:
    if total_buses > 0 and full_year_buses == total_buses and resize_recommendations > 0:
        return "demo_ready"
    if full_year_buses > 0:
        return "evidence_partial"
    return "screening_only"


def _bundle_context(bundle_dir: Path) -> BundleContext:
    manifest = _read_json(bundle_dir / "pipeline_manifest.json")
    request = manifest.get("request", {}) if isinstance(manifest.get("request"), dict) else {}
    evidence = manifest.get("evidence", {}) if isinstance(manifest.get("evidence"), dict) else {}
    requested_mw = _manifest_float(request.get("requested_mw"), default=5.0)
    return BundleContext(
        network_code=str(request.get("network_code") or "1-MV-rural--0-sw"),
        requested_mw=requested_mw,
        asset=str(request.get("asset") or "bess"),
        data_source_type=str(evidence.get("data_source_type") or "benchmark"),
        evidence_level=str(evidence.get("evidence_level") or "qsts_full_year"),
        decision_confidence=str(evidence.get("decision_confidence") or ""),
        recommended_next_action=str(evidence.get("recommended_next_action") or ""),
    )


def _manifest_float(value: object, default: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return default


def _decision_summary_rows(
    validation: list[dict[str, str]],
    qsts: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    if not validation and qsts:
        return [
            {
                "bus_id": row.get("bus_id", ""),
                "bus_name": row.get("bus_name", ""),
                "full_year_verdict": row.get("qsts_verdict", ""),
                "final_decision": row.get("product_decision") or row.get("qsts_verdict", ""),
                "validation_level": row.get("validation_level", ""),
                "decision_confidence": row.get("decision_confidence", ""),
                "recommended_next_action": row.get("recommended_next_action", ""),
                "dominant_constraint": row.get("main_recurring_constraint", ""),
            }
            for row in qsts
        ]
    return [
        {
            "bus_id": row.get("bus_id", ""),
            "bus_name": row.get("bus_name", ""),
            "screening_verdict": row.get("screening_verdict", ""),
            "stratified_verdict": row.get("qsts_stratified_verdict", ""),
            "full_year_verdict": row.get("qsts_full_year_verdict", ""),
            "final_decision": _primary_verdict(row),
            "calibration_status": row.get("calibration_status", ""),
            "recommended_next_action": row.get("recommended_next_action", ""),
            "dominant_constraint": row.get("main_recurring_constraint", ""),
        }
        for row in validation
    ]


def _evidence_boundary_heading(context: BundleContext) -> str:
    if context.data_source_type == "benchmark":
        return "Benchmark Status"
    return "Client Evidence Boundary"


def _render_evidence_boundary(context: BundleContext) -> str:
    if context.data_source_type == "benchmark":
        source_notice = (
            "This bundle uses a SimBench benchmark network. It proves the workflow and "
            "decision logic, not the feasibility of a real French site."
        )
        next_step = (
            "The commercial next step is to run the same workflow on a client, "
            "consultant, reconstructed public, or operator-validated network model "
            "with explicit data-source labels."
        )
    else:
        source_notice = (
            "This bundle is labelled with a non-benchmark data source. It remains a "
            "buyer-side pre-feasibility aid unless the assumptions and model are "
            "operator-validated."
        )
        next_step = (
            "Before commercial reliance, check model provenance, profile period, "
            "constraints, queue assumptions, and any operator feedback."
        )
    rows = [
        {
            "data_source_type": context.data_source_type,
            "evidence_level": context.evidence_level,
            "decision_confidence": context.decision_confidence,
            "recommended_next_action": context.recommended_next_action,
        }
    ]
    return (
        f'<p class="notice">{html.escape(source_notice)}</p>'
        f"<p>{html.escape(next_step)}</p>"
        "<p><strong>MVP Decision Policy:</strong> <code>docs/mvp-decision-policy.md</code>. "
        "The default investor-facing policy is <code>standard</code>; thresholds are "
        "VoltPath pre-feasibility assumptions, not official operator thresholds.</p>"
        + _html_table(rows)
    )


def _bundle_metrics(
    validation: list[dict[str, str]],
    resize: list[dict[str, str]],
    qsts: list[dict[str, str]],
    bundle_dir: Path,
) -> dict[str, object]:
    performance = _read_json(bundle_dir / "qsts_performance.json")
    evidence_rows = validation if validation else qsts
    total_buses = len(evidence_rows)
    if validation:
        full_year_buses = sum(1 for row in validation if row.get("qsts_full_year_verdict"))
        full_year_no_go = sum(1 for row in validation if _primary_verdict(row) == "no-go")
    else:
        full_year_buses = sum(
            1 for row in qsts if row.get("validation_level") == "qsts_full_year"
        )
        full_year_no_go = sum(
            1
            for row in qsts
            if (row.get("product_decision") or row.get("qsts_verdict")) == "no-go"
        )
    false_positive_stratified = sum(
        1 for row in validation if row.get("calibration_status") == "false_positive_stratified"
    )
    resize_recommendations = sum(
        1 for row in resize if row.get("product_decision") == "resize-recommended"
    )
    return {
        "full_year_coverage": f"{full_year_buses}/{total_buses} buses",
        "full_year_no_go": full_year_no_go,
        "false_positive_stratified": false_positive_stratified,
        "resize_recommendations": resize_recommendations,
        "runtime_minutes": float(performance.get("total_full_year_runtime_seconds", 0.0)) / 60,
    }


def _decision_sentence(metrics: dict[str, object], requested_mw: float) -> str:
    return (
        f"{metrics['full_year_coverage']} have full-year evidence. "
        f"{metrics['full_year_no_go']} buses are no-go under the selected policy at "
        f"{_format_mw_header(requested_mw)}, with "
        f"{metrics['resize_recommendations']} actionable resize recommendation."
    )


def _best_qsts_candidate(rows: list[dict[str, str]]) -> dict[str, str] | None:
    sorted_rows = _sorted_qsts_candidates(rows)
    return sorted_rows[0] if sorted_rows else None


def _sorted_qsts_candidates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=_qsts_sort_key)


def _qsts_sort_key(row: dict[str, str]) -> tuple[int, float, float, int | str]:
    decision_rank = {
        "go": 0,
        "go-with-conditions": 1,
        "resize-recommended": 2,
        "no-go": 3,
    }
    bus_id = row.get("bus_id", "")
    bus_key: int | str = int(bus_id) if bus_id.isdigit() else bus_id
    return (
        decision_rank.get(_qsts_decision(row), 9),
        _float_or_none(row.get("expected_curtailment_mwh") or row.get("weighted_curtailment_mwh")) or 0.0,
        _float_or_none(row.get("p90_curtailment_mw") or row.get("qsts_p90_curtailment_mw")) or 0.0,
        bus_key,
    )


def _qsts_decision(row: dict[str, str]) -> str:
    return row.get("product_decision") or row.get("qsts_verdict") or row.get("final_decision", "")


def _risk_for_bus(
    qsts_row: dict[str, str],
    risk_rows: list[dict[str, str]],
) -> dict[str, str]:
    bus_id = qsts_row.get("bus_id", "")
    if not bus_id:
        return {}
    for row in risk_rows:
        if row.get("bus_id") == bus_id:
            return row
    return {}


def _risk_text(
    risk: dict[str, str],
    fallback: dict[str, str],
    *keys: str,
) -> str:
    for key in keys:
        value = risk.get(key) or fallback.get(key)
        if value not in {None, ""}:
            return value
    return ""


def _risk_float(
    risk: dict[str, str],
    fallback: dict[str, str],
    *keys: str,
) -> float | None:
    return _float_or_none(_risk_text(risk, fallback, *keys))


def _bus_label(row: dict[str, str]) -> str:
    bus_id = row.get("bus_id", "")
    bus_name = row.get("bus_name", "")
    if bus_id and bus_name:
        return f"bus {bus_id} - {bus_name}"
    if bus_id:
        return f"bus {bus_id}"
    return bus_name or "candidate"


def _decision_label(decision: str) -> str:
    labels = {
        "go": "Proceed",
        "go-with-conditions": "Proceed with conditions",
        "resize-recommended": "Proceed after resize",
        "no-go": "Do not proceed at this size",
    }
    return labels.get(decision, decision or "Decision pending")


def _condition_instruction(constraint: str) -> str:
    normalized = constraint.lower()
    if "vm_pu.max" in normalized or "voltage high" in normalized:
        return "Limit export during rare high-voltage hours."
    if "vm_pu.min" in normalized or "voltage low" in normalized:
        return "Limit withdrawal during rare low-voltage hours."
    if "loading" in normalized or "thermal" in normalized or "line" in normalized:
        return "Respect a thermal loading envelope during constrained hours."
    return "Operate under the flexible envelope during constrained hours."


def _count_or_dash(rows: list[dict[str, str]]) -> str:
    return str(len(rows)) if rows else "-"


def _format_optional_number(value: float | None, unit: str) -> str:
    if value is None:
        return ""
    return f"{value:.2f} {unit}"


def _format_optional_mwh(value: float | None) -> str:
    if value is None:
        return "not available"
    return f"{value:.2f} MWh"


def _format_optional_mw(value: float | None) -> str:
    if value is None:
        return "not available"
    return f"{value:.2f} MW"


def _format_optional_hours(value: str) -> str:
    if not value:
        return ""
    parsed = _float_or_none(value)
    if parsed is None:
        return value
    return f"{parsed:.0f} h"


def _format_event(hours: str, mwh: float | None) -> str:
    hours_text = _format_optional_hours(hours)
    mwh_text = _format_optional_mwh(mwh)
    if not hours_text and mwh is None:
        return ""
    if not hours_text:
        return mwh_text
    if mwh is None:
        return hours_text
    return f"{hours_text} / {mwh_text}"


def _primary_verdict(row: dict[str, str]) -> str:
    return row.get("final_decision") or row.get("qsts_full_year_verdict", "")


def _badge(label: str, class_name: str) -> str:
    return f'<span class="badge {class_name}">{html.escape(label)}</span>'


def _artifact_link(filename: str) -> str:
    return f'<a href="{html.escape(filename)}">Open {html.escape(filename)}</a>'


def _render_decision_matrix(rows: list[dict[str, str]]) -> str:
    if not rows:
        return (
            "<p>No bus-by-MW sweep results available yet. Run "
            "<code>thesegrid qsts-sweep --config experiments/simbench_standard_policy_campaign_v1.json "
            "--output results/&lt;run_id&gt;</code>, then copy or aggregate "
            "<code>sensitivity_results.csv</code> into the investor bundle.</p>"
        )

    matrix: dict[str, dict[str, str]] = {}
    bus_names: dict[str, str] = {}
    requested_values: set[float] = set()
    for row in rows:
        if row.get("sampling_mode") not in {"", "stratified", "full_year"}:
            continue
        bus_id = row.get("bus_id", "")
        if not bus_id:
            continue
        requested_mw = _float_or_none(row.get("requested_mw"))
        if requested_mw is None:
            continue
        requested_values.add(requested_mw)
        bus_names[bus_id] = row.get("bus_name", "")
        verdict = row.get("qsts_verdict", "")
        p90 = row.get("qsts_p90_curtailment_mw", "")
        mwh = row.get("qsts_expected_curtailment_mwh", "")
        matrix.setdefault(bus_id, {})[_format_mw_header(requested_mw)] = (
            f"{verdict}<br><small>P90 {html.escape(p90)} MW / "
            f"{html.escape(mwh)} MWh</small>"
        )

    if not matrix:
        return "<p>No usable decision matrix rows available.</p>"

    mw_headers = [_format_mw_header(value) for value in sorted(requested_values)]
    header = "<th>bus_id</th><th>bus_name</th>" + "".join(
        f"<th>{html.escape(header)}</th>" for header in mw_headers
    )
    body_rows = []
    for bus_id in sorted(matrix, key=lambda value: int(value) if value.isdigit() else value):
        cells = [
            f"<td>{html.escape(bus_id)}</td>",
            f"<td>{html.escape(bus_names.get(bus_id, ''))}</td>",
        ]
        for header_label in mw_headers:
            cells.append(f"<td>{matrix[bus_id].get(header_label, '')}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _render_recommended_mw_by_bus(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No bus-by-MW recommendation rows available yet.</p>"

    best_by_bus: dict[str, dict[str, str]] = {}
    bus_names: dict[str, str] = {}
    seen_buses: set[str] = set()
    for row in rows:
        bus_id = row.get("bus_id", "")
        if not bus_id:
            continue
        seen_buses.add(bus_id)
        bus_names[bus_id] = row.get("bus_name", "")
        if row.get("qsts_verdict") not in {"go", "go-with-conditions"}:
            continue
        requested_mw = _float_or_none(row.get("requested_mw"))
        if requested_mw is None:
            continue
        current = best_by_bus.get(bus_id)
        current_mw = _float_or_none(current.get("recommended_mw") if current else None)
        if current is None or current_mw is None or requested_mw > current_mw:
            best_by_bus[bus_id] = {
                "recommended_mw": f"{requested_mw:.6f}",
                "qsts_verdict": row.get("qsts_verdict", ""),
                "sampling_mode": row.get("sampling_mode", ""),
                "qsts_p90_curtailment_mw": row.get("qsts_p90_curtailment_mw", ""),
                "qsts_expected_curtailment_mwh": row.get("qsts_expected_curtailment_mwh", ""),
                "main_recurring_constraint": row.get("main_recurring_constraint", ""),
            }

    table_rows: list[dict[str, str]] = []
    for bus_id in sorted(seen_buses, key=lambda value: int(value) if value.isdigit() else value):
        best = best_by_bus.get(bus_id)
        if best is None:
            table_rows.append(
                {
                    "bus_id": bus_id,
                    "bus_name": bus_names.get(bus_id, ""),
                    "recommended_mw": "",
                    "evidence_verdict": "no acceptable stratified MW",
                    "p90_mw": "",
                    "expected_mwh": "",
                    "recommended_next_action": "reject_or_test_lower_mw",
                }
            )
            continue
        verdict = best["qsts_verdict"]
        next_action = "run_full_year_validation"
        table_rows.append(
            {
                "bus_id": bus_id,
                "bus_name": bus_names.get(bus_id, ""),
                "recommended_mw": _format_mw_header(float(best["recommended_mw"])),
                "evidence_verdict": verdict,
                "p90_mw": best["qsts_p90_curtailment_mw"],
                "expected_mwh": best["qsts_expected_curtailment_mwh"],
                "recommended_next_action": next_action,
            }
        )
    return _html_table(table_rows)


def _render_full_year_conditional_checks(rows: list[dict[str, str]]) -> str:
    if not rows:
        return (
            "<p>No targeted full-year conditional validation rows are available yet. "
            "Use this section for cases that looked acceptable in stratified QSTS and "
            "need full-year confirmation.</p>"
        )
    return _html_table(rows)


def _frontier_rows(
    qsts_rows: list[dict[str, str]],
    full_year_conditional_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows = [_normalize_frontier_row(row) for row in qsts_rows]
    rows.extend(_normalize_frontier_row(row) for row in full_year_conditional_rows)
    return [row for row in rows if row]


def _normalize_frontier_row(row: dict[str, str]) -> dict[str, str]:
    requested_mw = _float_or_none(row.get("requested_mw"))
    p90_mw = _float_or_none(
        row.get("qsts_p90_curtailment_mw") or row.get("p90_curtailment_mw")
    )
    expected_mwh = _float_or_none(
        row.get("weighted_curtailment_mwh")
        or row.get("qsts_expected_curtailment_mwh")
        or row.get("expected_curtailment_mwh")
    )
    if requested_mw is None or p90_mw is None or expected_mwh is None:
        return {}
    theoretical_mwh = requested_mw * 8760.0
    energy_ratio = expected_mwh / theoretical_mwh if theoretical_mwh > 0 else 0.0
    p90_ratio = p90_mw / requested_mw if requested_mw > 0 else 0.0
    max_event_hours = int(float(row.get("max_event_hours") or 0))
    max_event_mwh = _float_or_none(row.get("max_event_mwh")) or 0.0
    max_event_mwh_per_mw = max_event_mwh / requested_mw if requested_mw > 0 else 0.0
    return {
        "bus_id": row.get("bus_id", ""),
        "bus_name": row.get("bus_name", ""),
        "requested_mw": _format_mw_header(requested_mw),
        "source_verdict": row.get("qsts_verdict", ""),
        "source_sampling": row.get("sampling_mode") or row.get("validation_level", ""),
        "p90_mw": f"{p90_mw:.6f}",
        "p90_curtailment_ratio": f"{p90_ratio:.3%}",
        "expected_mwh": f"{expected_mwh:.6f}",
        "curtailment_energy_ratio": f"{energy_ratio:.3%}",
        "max_event_hours": str(max_event_hours),
        "max_event_mwh_per_mw": f"{max_event_mwh_per_mw:.6f}",
        **{
            policy.name: frontier_verdict(
                p90_curtailment_ratio=p90_ratio,
                curtailment_energy_ratio=energy_ratio,
                max_event_hours=max_event_hours,
                max_event_mwh_per_mw=max_event_mwh_per_mw,
                policy=policy,
            )
            for policy in DECISION_FRONTIER_POLICIES
        },
    }


def _render_decision_frontier(rows: list[dict[str, str]]) -> str:
    if not rows:
        return (
            "<p>No full-year rows are available for decision-frontier analysis yet. "
            "Run targeted full-year validation before using this table.</p>"
        )
    return (
        "<p>This table reclassifies full-year evidence under several curtailment-risk "
        "policies. These are VoltPath policy assumptions for pre-feasibility, not "
        "official network-operator thresholds. The default investor policy is "
        "<code>standard</code>.</p>"
        + _html_table(_decision_policy_rows())
        + _html_table(rows)
    )


def _decision_policy_rows() -> list[dict[str, str]]:
    return [
        {
            "policy": policy.name,
            "policy_max_p90_ratio": f"{policy.max_p90_ratio:.6f}",
            "policy_max_energy_ratio": f"{policy.max_energy_ratio:.6f}",
            "policy_max_event_hours": str(policy.max_event_hours),
            "policy_max_event_mwh_per_mw": f"{policy.max_event_mwh_per_mw:.6f}",
            "status": "VoltPath policy assumption, not official threshold",
        }
        for policy in DECISION_FRONTIER_POLICIES
    ]


def _render_next_full_year_candidates(rows: list[dict[str, str]]) -> str:
    if not rows:
        return (
            "<p>No automatic full-year candidate selection is available yet. Run "
            "<code>thesegrid select-full-year-candidates</code> after screening and "
            "stratified QSTS.</p>"
        )
    return _html_table(rows)


def _render_recommended_resize(rows: list[dict[str, str]]) -> str:
    best = _best_resize_row(rows)
    if best is None:
        return "<p>No resize recommendation is available.</p>"
    original_mw = _float_or_none(best.get("original_requested_mw")) or 0.0
    recommended_mw = _float_or_none(best.get("requested_mw")) or 0.0
    delta_mw = recommended_mw - original_mw
    driver = best.get("verdict_driver", "")
    constraint = best.get("main_recurring_constraint", "")
    recommendations = _recommended_resize_rows(rows)
    summary = _html_table(
        [
            {
                "bus_id": _resize_bus_id(best),
                "Original request": f"{original_mw:.3f} MW",
                "Recommended size": f"{recommended_mw:.3f} MW",
                "Delta": f"{delta_mw:.3f} MW",
                "Decision": best.get("product_decision", ""),
                "Policy verdict": _selected_policy_verdict(best),
                "Main driver": driver,
                "Dominant constraint": constraint,
            }
        ]
    )
    return (
        "<h3>Resize Decision</h3>"
        + summary
        + "<h3>Resize Evidence</h3>"
        + _html_table(recommendations)
    )


def _best_resize_scorecard_line(rows: list[dict[str, str]]) -> str:
    best = _best_resize_row(rows)
    if best is None:
        return "none"
    original_mw = _float_or_none(best.get("original_requested_mw")) or 0.0
    recommended_mw = _float_or_none(best.get("requested_mw")) or 0.0
    return f"bus {_resize_bus_id(best)} from {original_mw:.3f} MW to {recommended_mw:.3f} MW"


def _best_resize_row(rows: list[dict[str, str]]) -> dict[str, str] | None:
    recommendations = _recommended_resize_rows(rows)
    if not recommendations:
        return None
    return max(
        recommendations,
        key=lambda row: (
            _float_or_none(row.get("original_requested_mw")) or 0.0,
            _float_or_none(row.get("requested_mw")) or 0.0,
        ),
    )


def _resize_bus_id(row: dict[str, str]) -> str:
    bus_id = row.get("bus_id", "")
    if bus_id:
        return bus_id
    match = re.search(r"bus(\d+)", row.get("scenario", ""))
    if match:
        return match.group(1)
    return ""


def _recommended_resize_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    best_by_key: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("product_decision") != "resize-recommended":
            continue
        key = row.get("bus_id") or row.get("scenario") or row.get("qsts_output_dir", "")
        if not key:
            key = str(len(best_by_key))
        current = best_by_key.get(key)
        row_mw = _float_or_none(row.get("requested_mw")) or 0.0
        current_mw = 0.0
        if current is not None:
            current_mw = _float_or_none(current.get("requested_mw")) or 0.0
        if current is None or row_mw > current_mw:
            best_by_key[key] = row
    return [
        {
            "bus_id": row.get("bus_id", ""),
            "scenario": row.get("scenario", ""),
            "original_requested_mw": row.get("original_requested_mw", ""),
            "recommended_mw": row.get("requested_mw", ""),
            "requested_mw": row.get("requested_mw", ""),
            "delta_mw_from_original": row.get("delta_mw_from_original", ""),
            "selected_policy": row.get("selected_policy", ""),
            "policy_verdict": _selected_policy_verdict(row),
            "product_decision": row.get("product_decision", ""),
            "expected_curtailment_mwh": row.get("expected_curtailment_mwh", ""),
            "p90_curtailment_mw": row.get("p90_curtailment_mw", ""),
            "verdict_driver": row.get("verdict_driver", ""),
            "main_recurring_constraint": row.get("main_recurring_constraint", ""),
            "delta_npv_eur": row.get("delta_npv_eur", ""),
        }
        for row in sorted(
            best_by_key.values(),
            key=lambda item: (item.get("bus_id", ""), item.get("scenario", "")),
        )
    ]


def _selected_policy_verdict(row: dict[str, str]) -> str:
    selected_policy = row.get("selected_policy", "")
    if selected_policy:
        verdict = row.get(f"{selected_policy}_policy_verdict", "")
        if verdict:
            return verdict
    if row.get("policy_verdict"):
        return row["policy_verdict"]
    return row.get("qsts_verdict", "")


def _format_mw_header(value: float) -> str:
    return f"{value:.0f} MW" if value.is_integer() else f"{value:.3f} MW"


def _float_or_none(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _economic_scenarios(bundle_dir: Path):
    return compare_economic_scenarios(
        qsts_rows=_read_csv(bundle_dir / "qsts_results.csv"),
        resize_rows=_read_csv(bundle_dir / "resize_results.csv"),
        assumptions=EconomicScenarioAssumptions(),
    )


def _gabarit_assumption_rows(bundle_dir: Path) -> list[dict[str, str]]:
    rows = _read_csv(bundle_dir / "gabarit_assumptions.csv")
    if rows:
        return rows
    return _stringify_rows(list(gabarit_rule_rows(rte_cre_inspired_v1_rules())))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _stringify_rows(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [{key: str(value) for key, value in row.items()} for row in rows]


def _html_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No rows available.</p>"
    columns = list(rows[0])
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(row.get(column, ''))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
