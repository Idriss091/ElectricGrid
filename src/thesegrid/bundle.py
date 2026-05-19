from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path

from thesegrid.economic_scenarios import (
    EconomicScenarioAssumptions,
    compare_economic_scenarios,
    economic_scenario_rows,
    render_economic_scenarios_markdown,
)


@dataclass(frozen=True)
class BundleReportPaths:
    html_path: Path
    scorecard_path: Path
    campaign_guide_path: Path
    economic_csv_path: Path
    economic_markdown_path: Path


def write_bundle_report(bundle_dir: Path) -> BundleReportPaths:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    html_path = bundle_dir / "investor_report.html"
    scorecard_path = bundle_dir / "scorecard.md"
    campaign_guide_path = bundle_dir / "next_calibration_campaign.md"
    economic_csv_path = bundle_dir / "economic_scenarios.csv"
    economic_markdown_path = bundle_dir / "economic_scenarios.md"
    economic_scenarios = _economic_scenarios(bundle_dir)
    _write_csv(economic_csv_path, economic_scenario_rows(economic_scenarios))
    economic_markdown_path.write_text(
        render_economic_scenarios_markdown(economic_scenarios, EconomicScenarioAssumptions()),
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
    no_go_full_year = sum(1 for row in validation if row.get("qsts_full_year_verdict") == "no-go")
    readiness = _readiness(total_buses, full_year_buses, resize_recommendations)
    runtime_seconds = float(performance.get("total_full_year_runtime_seconds", 0.0))

    return f"""# MVP Evidence Scorecard

- readiness: {readiness}
- full_year_coverage: {full_year_buses}/{total_buses} buses
- full_year_no_go: {no_go_full_year}
- false_positive_stratified: {false_positive_stratified}
- resize_recommendations: {resize_recommendations}
- full_year_runtime_minutes: {runtime_seconds / 60:.2f}
- qsts_result_rows: {len(qsts)}

## Interpretation

This bundle is demo-ready when all evaluated buses have full-year QSTS evidence and at
least one rejected site has an actionable resize recommendation. It remains a
buyer-side pre-feasibility aid and does not replace an official grid-connection study.
"""


def render_bundle_html(bundle_dir: Path) -> str:
    validation = _read_csv(bundle_dir / "validation_matrix.csv")
    resize = _read_csv(bundle_dir / "resize_results.csv")
    qsts = _read_csv(bundle_dir / "qsts_results.csv")
    economic_scenarios = _economic_scenarios(bundle_dir)
    scorecard = render_bundle_scorecard(bundle_dir)
    metrics = _bundle_metrics(validation, resize, qsts, bundle_dir)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Thesegrid BESS Investor Evidence</title>
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
    @media (max-width: 820px) {{
      main {{ padding: 22px 16px 42px; }}
      .hero, .kpis, .artifact-grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 34px; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div>
        <h1>Thesegrid BESS Investor Evidence</h1>
        <p>Flexible-connection pre-feasibility for a 5 MW BESS candidate set on SimBench network <strong>1-MV-rural--0-sw</strong>.</p>
        <p class="notice">This is a buyer-side pre-feasibility aid, not an official grid-connection study, PTF, or RTE/Enedis offer.</p>
      </div>
      <aside class="panel">
        <h3>Investment Decision</h3>
        <p>{_decision_sentence(metrics)}</p>
        <p>{_badge("no-go", "badge-no-go")} {_badge("resize-recommended", "badge-resize")} {_badge("full-year evidence", "badge-evidence")}</p>
      </aside>
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

    <section>
      <h2>Scorecard</h2>
      <div class="scorecard">{html.escape(scorecard)}</div>
    </section>

    <section>
      <h2>Evidence Tables</h2>
      <h3>Validation Matrix</h3>
      {_html_table(validation)}
      <h3>Full-Year QSTS Results</h3>
      {_html_table(qsts)}
      <h3>Resize Evidence</h3>
      {_html_table(resize)}
    </section>

    <section>
      <h2>Proxy Economics</h2>
      <p class="notice">This is proxy economics, not bankable revenue modelling. Values are scenario-comparison aids only.</p>
      {_html_table(_stringify_rows(economic_scenario_rows(economic_scenarios)))}
    </section>

    <section>
      <h2>Bundle Artifacts</h2>
      <div class="artifact-grid">
        {_artifact_link("validation_matrix.csv")}
        {_artifact_link("resize_results.csv")}
        {_artifact_link("economic_scenarios.csv")}
        {_artifact_link("qsts_results.csv")}
        {_artifact_link("qsts_risk_summary.csv")}
        {_artifact_link("contractual_envelope.csv")}
        {_artifact_link("run_manifest.json")}
      </div>
    </section>
  </main>
</body>
</html>
"""


def render_next_calibration_campaign(bundle_dir: Path) -> str:
    validation = _read_csv(bundle_dir / "validation_matrix.csv")
    candidate_buses = ", ".join(row.get("bus_id", "") for row in validation if row.get("bus_id"))
    return f"""# Next Calibration Campaign

## Goal

Expand the current BESS evidence beyond the first investor bundle while keeping the V1
focused on BESS France and buyer-side pre-feasibility.

## Recommended Matrix

- Network: add 1-2 additional SimBench MV networks after `1-MV-rural--0-sw`.
- Buses: start with current evidence buses ({candidate_buses}) and the top 3 buses from each new screening.
- Requested MW values: 2, 3, 5, and 7 MW.
- Tolerances: P90 = 0, 1, 3 MW; expected MWh = 0, 60, 120 MWh.
- Evidence levels: screening, stratified QSTS, and full-year QSTS for cases where stratified evidence is acceptable or ambiguous.

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


def _bundle_metrics(
    validation: list[dict[str, str]],
    resize: list[dict[str, str]],
    qsts: list[dict[str, str]],
    bundle_dir: Path,
) -> dict[str, object]:
    del qsts
    performance = _read_json(bundle_dir / "qsts_performance.json")
    total_buses = len(validation)
    full_year_buses = sum(1 for row in validation if row.get("qsts_full_year_verdict"))
    full_year_no_go = sum(1 for row in validation if row.get("qsts_full_year_verdict") == "no-go")
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


def _decision_sentence(metrics: dict[str, object]) -> str:
    return (
        f"{metrics['full_year_coverage']} have full-year evidence. "
        f"{metrics['full_year_no_go']} buses are no-go at 5 MW, with "
        f"{metrics['resize_recommendations']} actionable resize recommendation."
    )


def _badge(label: str, class_name: str) -> str:
    return f'<span class="badge {class_name}">{html.escape(label)}</span>'


def _artifact_link(filename: str) -> str:
    return f'<a href="{html.escape(filename)}">Open {html.escape(filename)}</a>'


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
