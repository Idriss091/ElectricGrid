# Product specification

## Users

Primary V1 users:

- BESS developers;
- grid-connection consultants;
- BESS site-selection and investment teams.

Large loads, data centers, hydrogen, industrial flexibility, and utility-wide digital
twins are outside the V1 wedge.

## Inputs

- Candidate site or connection bus
- Requested MW
- Asset type
- Operating assumptions
- Curtailment tolerance
- Reinforcement waiting time assumption
- Economic assumptions

## Outputs

- Maximum firm capacity
- Maximum conditional capacity accepted up to the requested MW
- Evaluated conditional MW used for the risk and economic estimate
- Recommended flexible connection envelope
- RTE/CRE-inspired gabarit rule rows with source labels and validity dates
- Envelope comparison across firm-only, RTE-inspired, and custom envelopes
- Expected curtailment hours
- P50/P90 curtailment estimate
- EBITDA-at-risk estimate
- Go / no-go / go-with-conditions recommendation
- Resize-recommended decision when the requested MW is rejected but a lower tested MW is
  QSTS-acceptable
- Automated investment memo
- Pipeline command that runs static screening, stratified candidate selection, and
  optionally stratified QSTS behind an explicit flag, then selects full-year QSTS
  finalists and optionally runs full-year QSTS behind a second explicit flag
- Reproducible full-pipeline demo runbook in `docs/demo-pipeline.md`
- QSTS bundle with `investment_memo.md`, `run_manifest.json`, `qsts_performance.json`,
  `static_vs_qsts_comparison.csv`, and contractual-envelope CSVs
- Validation matrix comparing screening, QSTS short, QSTS stratified, and QSTS full-year
  verdicts
- Decision confidence fields: `validation_level`, `decision_confidence`, and
  `recommended_next_action`
- QSTS sensitivity sweep outputs for comparing verdict thresholds across requested MW,
  curtailment tolerance, and voltage assumptions
- QSTS resize outputs that test lower MW values and recommend the largest acceptable
  resized connection size, delta MW from the original request, verdict driver, dominant
  constraint, and proxy delta NPV
- Performance fields including evaluated bus-hours and power-flow calls per bus-hour

## V1 limitation

The V1 focuses on pre-feasibility.
It does not replace the official network operator connection study.
Screening, short QSTS, and stratified QSTS are triage or pre-demo evidence. Full-year
QSTS is the MVP investor reference layer, not an official study.
The economic layer is a proxy, not bankable revenue modelling.
