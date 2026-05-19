# Research protocol

## Objective

The shared product and paper objective is to convert BESS hosting capacity into an
investment-grade flexible connection proposal:

- firm MW;
- conditional MW;
- operating envelope;
- curtailment risk;
- economic verdict.

## Reproducible experiment sequence

1. Select a SimBench benchmark network and record the exact network code.
2. Select candidate connection buses and record bus ids.
3. Run firm-capacity binary search for injection and withdrawal.
4. Identify binding voltage, line, and transformer constraints.
5. Apply the two French V1 gabarits and the custom envelope fallback.
   The French V1 gabarits must be represented as explicit rule objects with source
   labels, validity date, season, time block, direction, allowed value, and prudence
   level.
6. Estimate curtailment hours, MWh, P50, and P90 at the evaluated requested MW.
7. Search the maximum conditional MW accepted under curtailment tolerance and positive
   flexible-value proxy.
8. Compare connect-now-flexible against wait-for-reinforcement using configurable
   economic proxies.
9. Emit a machine-generated memo into `results/<run_id>/memo.md`.
10. For top-ranked buses, run QSTS validation using SimBench profiles before making
    claims about hourly envelope feasibility.
11. Record a machine-readable run manifest for every QSTS output directory so the
    experiment can be reproduced from the command, request, settings, environment, and
    git metadata.
12. Compare short and stratified QSTS against one or more full-year QSTS runs with a
    validation matrix before making investor-grade claims.

## Multi-bus screening experiment

The first repeatable product/science experiment is a multi-bus BESS screening run:

1. Select one SimBench network code.
2. Select one requested BESS MW value.
3. Select active MV candidate buses and exclude slack or external-grid buses.
4. Run the mono-bus assessment for each candidate bus.
5. Rank buses by investment decision quality:
   verdict, flexible value delta, conditional capacity, P90 curtailment, then firm
   capacity.
6. Write `screening.csv` for analysis and `screening_summary.md` for the product-style
   decision narrative.

This screening is the bridge between the commercial site-selection workflow and the
paper's benchmark tables. It remains a pre-feasibility proxy until time-series/QSTS
validation is added for the best-ranked buses.

## QSTS validation experiment

The first QSTS workflow validates top-ranked BESS candidates from a screening CSV:

1. Load `screening.csv` and select the top N rows by screening rank.
2. Load the same SimBench network and its annual load, generation, and storage
   profiles.
3. Convert sub-hourly SimBench profiles to hourly profiles when needed for the MVP
   validation run.
4. For each selected bus and each time step, evaluate BESS injection and withdrawal.
5. Run a no-candidate baseline for the same time step, then classify candidate
   violations as pre-existing, worsened, or new.
6. Record convergence, voltage, line loading, transformer loading, feasible MW,
   curtailed MW, raw binding constraint, and incremental binding constraint.
7. Summarize the worst directional curtailment per timestamp as QSTS expected hours,
   MWh, P50, P90, P95, P99, max MW, and maximum consecutive curtailment event.
8. Classify `go-with-conditions` only when QSTS P90 curtailed MW and expected curtailed
   MWh are within the configured QSTS curtailment tolerances.
9. Use stratified QSTS sampling for bounded annual campaigns when full-year validation is
   not yet practical, so samples cover month and contractual time-block diversity instead
   of aliasing to a single hour of day.
10. Synthesize a compact contractual envelope from the QSTS-derived hourly envelope using
   RTE-inspired V1 seasons, fixed time blocks, and P10 allowed MW as the conservative
   recommended value.
11. Write `qsts_results.csv`, `investor_decision.csv`, `qsts_risk_summary.csv`,
    `qsts_risk_summary.json`, `qsts_summary.md`, `qsts_envelope.csv`,
    `qsts_envelope_summary.csv`, `contractual_envelope.csv`, and per-bus detail CSV files.
12. Write `investment_memo.md` as the investor-facing QSTS decision memo and
    `run_manifest.json` as the reproducibility record for the generated bundle.
13. Write `qsts_performance.json`, `static_vs_qsts_comparison.csv`, and
    `annual_validation_summary.md` so annual and sampled-annual campaigns expose both
    scientific metrics and runtime cost.
14. For calibrated demo cases, write `validation_matrix.csv` and `validation_matrix.md`
    to compare screening, short QSTS, stratified QSTS, and full-year QSTS verdicts.
15. For the investor MVP calibration campaign, use `experiments/investor_mvp_calibration.json`
    as the scenario definition unless a newer dated experiment file supersedes it.

QSTS output must state that it is based on actual hourly power-flow validation and
that verdicts are baseline-aware. It must also state that the study still excludes
short-circuit, protection, dynamic stability, N-1 security, harmonic limits, and
official operator planning criteria.

## Product outputs

The product MVP must emit:

- maximum firm injection and withdrawal capacity;
- headline firm capacity;
- maximum conditional capacity accepted up to the requested MW;
- evaluated conditional MW used for the risk and economic estimate;
- recommended envelope;
- envelope comparison across firm-only, RTE-inspired, and custom envelopes;
- binding constraints;
- expected curtailment;
- EBITDA-at-risk proxy;
- go / no-go / go-with-conditions recommendation.

For multi-bus screening, the product also emits:

- ranked candidate bus table;
- top-10 decision summary;
- verdict distribution;
- most frequent binding constraints.

For QSTS validation, the product emits:

- top-N QSTS validation table;
- investor-facing `investment_memo.md` with primary recommendation, QSTS decision table,
  decision drivers, contractual-envelope summary, economics proxy, assumptions, and
  remaining exclusions;
- investor decision CSV with verdict, firm/conditional MW, QSTS P90 MW, expected MWh,
  and main recurring constraint;
- per-bus hourly detail files;
- comparison fields linking static firm/conditional capacity to QSTS curtailment;
- validation matrix outputs that identify false positives, missing full-year validation,
  and final decisions;
- the QSTS P90 MW and expected MWh curtailment tolerances used for the verdict;
- `qsts_risk_summary.csv` and `qsts_risk_summary.json` with P95/P99/max risk,
  consecutive-event metrics, verdict driver, and tail-risk flag;
- a contractual-envelope table that distinguishes conservative P10 allowed MW from
  diagnostic P25/P50/min allowed MW and P90 curtailed MW;
- explicit distinction between proxy screening results and actual hourly power-flow
  validation;
- `run_manifest.json` with the CLI invocation, request, constraint settings, generated
  outputs, Python/platform metadata, package version, and git state.
- `qsts_performance.json` with runtime seconds, power-flow calls, binary-search count,
  baseline cache hits/misses, evaluated buses, evaluated bus-hours, power-flow calls per
  bus-hour, runtime seconds per bus-hour, and the declared parallelization unit.
- `static_vs_qsts_comparison.csv` for direct proxy-vs-QSTS comparison.

## QSTS sensitivity sweep

The first sensitivity workflow is:

```bash
thesegrid qsts-sweep --config sweep.json --output results/<run_id>
```

The sweep config varies requested MW, QSTS P90 tolerance, expected-MWh tolerance, voltage
max, and optionally `sampling_modes`, `bus_ids`, `start_hour`, `duration_hours`, and
`sample_every_n_hours`. `sampling_modes` can compare `stratified` against `full_year`;
if absent, the legacy `sampling` field is used. The sweep writes
`sensitivity_results.csv`, `sampling_calibration.csv`, `sensitivity_summary.md`,
`sweep_manifest.json`, and one QSTS output subdirectory per scenario.

## Scientific outputs

The paper should use the same experiment outputs to build:

- a formal definition of flexible interconnection envelope synthesis;
- a benchmark study over multiple buses and networks;
- sensitivity analysis over curtailment tolerance, waiting time, and economic proxies;
- QSTS comparison of static proxy curtailment against time-varying SimBench operating
  points;
- a limitations section separating pre-feasibility from official network studies.

## Reproducibility rules

- Every run must record network code, bus id, requested MW, economic assumptions, and
  constraint settings.
- QSTS output directories must include `run_manifest.json`; if the working tree is dirty,
  that state is recorded instead of silently treating the run as a clean benchmark.
- Sensitivity sweeps must preserve per-scenario QSTS output directories instead of only
  writing aggregate CSVs.
- Raw sources stay in `papers/` or `Scientific-Pappers/`.
- Code stays in `src/`.
- Tests stay in `tests/`.
- Generated memos and experiment outputs stay in `results/`.
