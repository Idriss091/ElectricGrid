# Interpretation Guide

This guide explains the main outputs in the BESS flexible-connection demo. It is written
for readers who do not need to inspect the source code.

## Verdicts

- `go`: requested MW is feasible without observed QSTS curtailment.
- `go-with-conditions`: requested MW is acceptable only under a flexible envelope and
  within the configured curtailment tolerances.
- `no-go`: requested MW exceeds firm or conditional acceptance, or the QSTS risk exceeds
  at least one configured tolerance.

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
- `curtailment_p95_mw`, `curtailment_p99_mw`, `curtailment_max_mw`: tail-risk metrics
  used to expose rare but severe events.
- `max_event_hours` and `max_event_mwh`: longest contiguous curtailment event and its
  curtailed energy.
- `main_recurring_constraint` or `dominant_constraint`: most frequent candidate-caused
  network constraint.
- `validation_level`: evidence layer behind the verdict.
- `decision_confidence`: `low`, `medium`, or `high`, based on the validation level.
- `recommended_next_action`: next product action before using the verdict commercially.
- `evaluated_bus_hours`: QSTS bus-time workload metric used for runtime planning.
- `power_flow_calls_per_bus_hour`: rough compute intensity indicator for full-year
  validation campaigns.

## Important Files

- `screening.csv`: ranked static screening table for candidate buses.
- `screening_summary.md`: human-readable static screening summary.
- `qsts_results.csv`: QSTS verdict and core risk metrics per evaluated bus.
- `qsts_risk_summary.csv`: tail-risk and verdict-driver diagnostics.
- `qsts_envelope.csv`: hourly QSTS-derived allowed MW and curtailed MW.
- `contractual_envelope.csv`: compact direction, season, and time-block envelope.
- `static_vs_qsts_comparison.csv`: direct comparison between static proxy and QSTS
  validation.
- `investment_memo.md`: investor-facing recommendation.
- `run_manifest.json`: reproducibility record with request, settings, outputs,
  environment, package version, and git state.
- `qsts_performance.json`: runtime and power-flow counter diagnostics.
- `experiments/investor_mvp_calibration.json`: canonical MVP calibration sweep config.

## France BESS Language

Thesegrid uses RTE/CRE-inspired vocabulary for the France BESS wedge: PTF, gabarit
injection/soutirage, capacite d'accueil, zone contrainte, and offre optimisee. These
terms are interpretive labels for buyer-side pre-feasibility. The generated memo is not
a PTF, not an official RTE/Enedis offer, and not an official connection study.

## Reading The Demo Result

In `results/demo_investor_2026-05-18/qsts_representative_stratified_tol3_mwh60/`:

- Bus 2 is a `go`: QSTS P90 MW is 0 and expected curtailed MWh is 0.
- Bus 21 is a `no-go`: QSTS P90 MW is 2.148 MW, within the 3 MW tolerance, but expected
  curtailed energy is 165.703 MWh, above the 60 MWh tolerance.
- Bus 24 is a `no-go`: QSTS P90 MW is 2.617 MW, within the 3 MW tolerance, but expected
  curtailed energy is 206.094 MWh, above the 60 MWh tolerance.

This is the main decision lesson: a site can look acceptable on P90 MW while still being
unacceptable on annual or sampled curtailed energy.

The full-year calibration run under
`results/demo_investor_2026-05-18/qsts_bus2_full_year_tol3_mwh60/` strengthens that
lesson. Bus 2 changes from stratified `go` to full-year `no-go`: QSTS P90 MW remains
0, but expected curtailed energy reaches 120.977 MWh across 52 curtailment hours. The
dominant incremental constraint is high voltage around bus 15.

Use the stratified run for quick triage and explanation. Use the full-year run when the
decision needs a stronger annual-risk basis.

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
