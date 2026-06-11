# Interpretation Guide

This guide explains the main outputs in the BESS flexible-connection demo. It is written
for readers who do not need to inspect the source code.

## Verdicts

- `go`: requested MW is feasible without observed QSTS curtailment.
- `go-with-conditions`: requested MW is acceptable only under a flexible envelope and
  within the configured curtailment tolerances.
- `no-go`: requested MW exceeds firm or conditional acceptance, or the QSTS risk exceeds
  at least one configured tolerance.

`qsts_verdict` is a legacy QSTS verdict based on configured absolute P90 MW and MWh
tolerances. When `decision_frontier.csv` is available, the investor-facing verdict should
come from the selected policy frontier, defaulting to `standard`. Use `flexible` as an
explicit alternative commercial appetite, not as a silent replacement for the default
decision.

QSTS verdicts are baseline-aware. Pre-existing network violations are reported, but they
do not trigger candidate curtailment unless the BESS creates a new violation or worsens an
existing one.

Use `docs/decision-policy.md` for the current rule that separates `screening_only`,
`qsts_short`, `qsts_stratified`, and `qsts_full_year` conclusions.

## Core Metrics

- `static_firm_capacity_mw`: maximum steady-state firm MW from the static screening.
- `static_conditional_capacity_mw`: maximum accepted MW under the static flexible-envelope
  proxy.
- `qsts_p90_curtailment_mw`: 90th percentile of QSTS curtailed MW.
- `expected_curtailment_mwh`: total curtailed MWh over the evaluated QSTS sample.
- `sampled_curtailment_mwh`: raw curtailed MWh over evaluated timestamps.
- `weighted_curtailment_mwh`: curtailed MWh used for the QSTS verdict; stratified
  samples are weighted to represent month/time-block exposure.
- `curtailment_energy_ratio`: weighted curtailed MWh divided by requested annual MWh.
- `p90_curtailment_ratio`: QSTS P90 MW divided by requested MW, used by the decision
  frontier to compare projects of different sizes.
- `curtailment_p95_mw`, `curtailment_p99_mw`, `curtailment_max_mw`: tail-risk metrics
  used to expose rare but severe events.
- `max_event_hours` and `max_event_mwh`: longest contiguous curtailment event and its
  curtailed energy.
- `max_event_mwh_per_mw`: longest event energy normalized by requested MW.
- `main_recurring_constraint` or `dominant_constraint`: most frequent candidate-caused
  network constraint.
- `validation_level`: evidence layer behind the verdict.
- `decision_confidence`: `low`, `medium`, or `high`, based on the validation level.
- `recommended_next_action`: next product action before using the verdict commercially.
- `evaluated_bus_hours`: QSTS bus-time workload metric used for runtime planning.
- `evaluated_time_steps`: unique timestamps evaluated; this is distinct from bus-hours.
- `power_flow_calls_per_bus_hour`: rough compute intensity indicator for full-year
  validation campaigns.

## Important Files

- `screening.csv`: ranked static screening table for candidate buses.
- `screening_summary.md`: human-readable static screening summary.
- `qsts_results.csv`: QSTS verdict and core risk metrics per evaluated bus.
- `qsts_risk_summary.csv`: tail-risk and verdict-driver diagnostics.
- `qsts_economics.csv`: per-bus proxy economics.
- `decision_frontier.csv`: strict, standard, flexible, and aggressive policy
  reclassification using weighted MWh and energy ratio.
- `validation_matrix.csv`: selected-policy final decision plus the legacy QSTS verdict
  for comparison.
- `qsts_envelope.csv`: hourly QSTS-derived allowed MW and curtailed MW.
- `contractual_envelope.csv`: compact direction, season, and time-block envelope.
- `static_vs_qsts_comparison.csv`: direct comparison between static proxy and QSTS
  validation.
- `investment_memo.md`: investor-facing recommendation.
- `run_manifest.json`: reproducibility record with request, settings, outputs,
  environment, package version, and git state.
- `qsts_performance.json`: runtime and power-flow counter diagnostics.
- `experiments/simbench_standard_policy_campaign_v1.json`: current multi-network
  calibration campaign definition.

## France BESS Language

VoltPath uses RTE/CRE-inspired vocabulary for the France BESS wedge: PTF, gabarit
injection/soutirage, capacite d'accueil, zone contrainte, and offre optimisee. These
terms are interpretive labels for buyer-side pre-feasibility. The generated memo is not
a PTF, not an official RTE/Enedis offer, and not an official connection study.

## Reading Current Results

Current generated results are local artifacts under `results/`. Regenerate a single
demo with `docs/demo-pipeline.md`, or use
`experiments/simbench_standard_policy_campaign_v1.json` for the current multi-network
calibration campaign.

For investor-facing decisions, read `decision_frontier.csv` and the selected-policy
fields in `validation_matrix.csv`. The default selected policy is `standard`, which
uses ratio-based thresholds rather than fixed MW/MWh values.

Use stratified QSTS for quick triage and comparison. Use full-year QSTS when the decision
needs a stronger annual-risk basis.

## Contractual Envelope

The contractual envelope is a compact pre-feasibility synthesis. It is not an official
RTE operating gabarit.

- `allowed_mw_p10`: conservative allowed MW used as the recommended contract-like value.
- `allowed_mw_p25` and `allowed_mw_p50`: diagnostic less-conservative alternatives.
- `allowed_mw_min`: most restrictive observed allowed MW in the group.
- `curtailed_mw_p90`: risk indicator for that direction, season, and time block.

For the demo, bus 2 keeps 5 MW in all blocks. Buses 21 and 24 show materially reduced
injection envelopes while withdrawal remains unconstrained in the evaluated sample.

## Limits

The demo excludes short-circuit, protection, dynamic stability, N-1 security, harmonics,
and official operator planning criteria. It is a buyer-side pre-feasibility aid, not a
bankable or official connection study.
