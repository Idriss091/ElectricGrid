# Current State and QSTS Next Steps

Status: historical working log. For the current source of truth, use
`docs/project-status-2026-05-18.md`.

Historical result paths referenced before the 2026-05-18 canonical demo cleanup now live
under `results/archive/legacy_2026-05-18/`.

Date: 2026-05-13

## Purpose

This document records the current state of the BESS pre-feasibility MVP after the
latest QSTS audit. It summarizes what was tested, what now works, what remains weak,
and what should be implemented next.

The project remains a buyer-side decision engine for flexible grid-connection
pre-feasibility. It does not replace an official grid-connection study.

## Current Product State

The MVP can now:

- assess one candidate BESS connection bus;
- estimate firm injection and withdrawal capacity;
- estimate accepted conditional capacity up to the requested MW;
- compare firm-only, RTE-inspired gabarits, and a custom envelope;
- estimate static proxy curtailment with expected MWh, P50, and P90 metrics;
- estimate a configurable connect-now versus wait-for-reinforcement economic proxy;
- return a `go`, `go-with-conditions`, or `no-go` verdict for the static assessment;
- screen multiple MV candidate buses and rank them in CSV and Markdown outputs;
- run a QSTS validation workflow on selected screened buses;
- compute QSTS curtailment from hourly power-flow replay;
- classify QSTS violations incrementally against a no-candidate baseline;
- reuse no-candidate QSTS baseline states across buses in the same run;
- use optional stratified QSTS sampling to cover month/time-block diversity in bounded
  annual campaigns;
- apply an explicit QSTS P90 curtailment tolerance to the QSTS verdict;
- export a compact investor decision table in `investor_decision.csv`;
- export a QSTS-derived hourly flexible envelope in `qsts_envelope.csv`;
- export a compact month/hour/direction envelope in `qsts_envelope_summary.csv`;
- export an investor-facing contractual envelope in `contractual_envelope.csv`, grouped by
  direction, RTE-inspired V1 season, and fixed time block;
- export a QSTS investor memo in `investment_memo.md`;
- export a reproducibility manifest in `run_manifest.json`;
- export QSTS runtime and power-flow counters in `qsts_performance.json`;
- export tail-risk diagnostics in `qsts_risk_summary.csv` and `qsts_risk_summary.json`;
- export static-vs-QSTS comparison metrics in `static_vs_qsts_comparison.csv`;
- export `annual_validation_summary.md` for full-year or sampled-annual bundles;
- run QSTS sensitivity sweeps with `thesegrid qsts-sweep`;
- compare firm-only, static custom, RTE-inspired, and QSTS-derived envelopes in
  `qsts_summary.md`;
- record QSTS baseline diagnostics and runtime constraint settings.

The main user-facing commands are:

```bash
thesegrid assess --network <network_code> --bus <bus_id> --requested-mw <mw> --output <memo_path>
thesegrid screen --network <network_code> --requested-mw <mw> --output <output_dir>
thesegrid qsts --network <network_code> --screening-csv <screening_csv> --requested-mw <mw> --top-n <n> --bus-ids <id,id> --start-hour <h> --duration-hours <h> --sample-every-n-hours <n> --stratified-sample --voltage-min-pu <pu> --voltage-max-pu <pu> --max-loading-percent <percent> --p90-curtailment-tolerance-mw <mw> --expected-curtailment-tolerance-mwh <mwh> --progress-every-n-hours <n> --storage-duration-hours <h> --capex-eur-per-kw <eur> --fixed-opex-eur-per-kw-year <eur> --gross-revenue-eur-per-mw-year <eur> --curtailment-penalty-eur-per-mwh <eur> --reinforcement-wait-years <years> --discount-rate <rate> --output <output_dir>
thesegrid qsts-sweep --config <sweep_json> --output <output_dir>
```

## Verification Performed

The latest automated checks before the risk-summary tranche passed after the QSTS
performance and sweep implementation:

- `python -m pytest -q`: 54 passed, 1 skipped;
- `.venv/bin/python -m pytest -q`: 55 passed;
- `python -m ruff check .`: passed.

The `.venv` run includes SimBench-dependent tests.

## Latest Audit Runs

Latest generated benchmark outputs are under:

- `results/qsts_performance_2026-05-13/`.

The earlier envelope audit remains under `results/qsts_envelope_2026-05-09/`.

The canonical investor-demo run is under:

- `results/demo_investor_2026-05-18/`.

It uses SimBench network `1-MV-rural--0-sw`, a 5 MW BESS request, representative buses
2, 21, and 24, QSTS P90 curtailment tolerance of 3 MW, and QSTS expected curtailed-energy
tolerance of 60 MWh. The run includes static screening, stratified QSTS validation,
QSTS risk summary, contractual envelope export, static-vs-QSTS comparison, investor
memo, reproducibility manifest, and performance counters.

It also includes a full-year top-1 QSTS calibration run for bus 2 with the same
tolerances:

- `results/demo_investor_2026-05-18/qsts_bus2_full_year_tol3_mwh60/`.

### Toy Network

The toy network remains useful for deterministic smoke tests. It verifies that the
core decision logic can produce all static verdict classes:

| Case | Expected static result |
| --- | --- |
| `toy`, bus 1, 4 MW | `go` |
| `toy`, bus 1, 5.5 MW, P90 tolerance 1 MW | `go-with-conditions` |
| `toy`, bus 1, 8 MW, P90 tolerance 1 MW | `no-go` |

QSTS intentionally refuses the `toy` network because QSTS requires SimBench-style
time-series profiles.

### Static SimBench Screening

The SimBench network `1-MV-rural--0-sw` was screened at 5 MW.

Output:

- `results/qsts_envelope_2026-05-09/screen_5mw/screening.csv`;
- `results/qsts_envelope_2026-05-09/screen_5mw/screening_summary.md`.

Result:

The top three static candidates remain buses 2, 3, and 16, each with 5 MW firm and
conditional capacity in the static screening.

Frequent static constraints include:

- high voltage around buses 59, 89, 42, 72, 21, and 14;
- thermal overload on `line[0] MV1.101 Line 1` for several candidate buses.

### QSTS Top-3 Validation

The top 3 screened buses were validated over the first 24 hourly steps with
baseline-aware QSTS.

Outputs:

- `results/qsts_envelope_2026-05-09/qsts_top3_24h_tol3/qsts_results.csv`;
- `results/qsts_envelope_2026-05-09/qsts_top3_24h_tol3/qsts_envelope.csv`;
- `results/qsts_envelope_2026-05-09/qsts_top3_24h_tol3/qsts_envelope_summary.csv`;
- `results/qsts_envelope_2026-05-09/qsts_top3_24h_tol3/qsts_summary.md`.

Result:

| bus | QSTS P90 tolerance MW | QSTS verdict | QSTS P90 MW | QSTS MWh |
| ---: | ---: | --- | ---: | ---: |
| 2 | 3 | `go` | 0.000 | 0.000 |
| 3 | 3 | `go` | 0.000 | 0.000 |
| 16 | 3 | `go` | 0.000 | 0.000 |

These top buses remain robust in the first 24-hour QSTS window.

### Representative QSTS Validation

Three representative buses were validated over the first 24 hourly steps:

- bus 2: top static `go`;
- bus 21: constrained high-voltage bus from the static ranking;
- bus 24: first static `no-go`.

Outputs:

- `results/qsts_envelope_2026-05-09/qsts_representative_24h_tol3/qsts_results.csv`;
- `results/qsts_envelope_2026-05-09/qsts_representative_24h_tol3/qsts_envelope.csv`;
- `results/qsts_envelope_2026-05-09/qsts_representative_24h_tol3/qsts_envelope_summary.csv`;
- `results/qsts_envelope_2026-05-09/qsts_representative_24h_tol3/qsts_summary.md`.

Result:

| bus | Static verdict | QSTS tolerance MW | QSTS verdict | QSTS P90 MW | QSTS MWh | recurring incremental constraint |
| ---: | --- | ---: | --- | ---: | ---: | --- |
| 2 | `go` | 3 | `go` | 0.000 | 0.000 | none |
| 21 | `no-go` | 3 | `go-with-conditions` | 2.098 | 45.469 | new high voltage at bus 20 |
| 24 | `no-go` | 3 | `go-with-conditions` | 2.566 | 57.188 | new high voltage at bus 20 |

The QSTS tolerance materially changes the investment conclusion. QSTS now treats
`go-with-conditions` as a user-defined curtailment appetite, and the exported
QSTS-derived envelope shows the allowed MW hour by hour.

### Sampled Annual QSTS

A sampled annual run was executed for the top 3 screened buses with
`--sample-every-n-hours 168`, which evaluates one hourly operating point per week.

Outputs:

- `results/qsts_envelope_2026-05-09/qsts_top3_sample168_tol3/qsts_results.csv`;
- `results/qsts_envelope_2026-05-09/qsts_top3_sample168_tol3/qsts_envelope.csv`;
- `results/qsts_envelope_2026-05-09/qsts_top3_sample168_tol3/qsts_envelope_summary.csv`;
- `results/qsts_envelope_2026-05-09/qsts_top3_sample168_tol3/qsts_summary.md`.

Result:

| bus | evaluated hours | QSTS verdict | QSTS P90 MW | QSTS MWh | violation hours |
| ---: | ---: | --- | ---: | ---: | ---: |
| 2 | 53 | `go` | 0.000 | 0.625 | 2 |
| 3 | 53 | `go` | 0.000 | 0.625 | 2 |
| 16 | 53 | `go` | 0.000 | 0.156 | 1 |

This run is not a full annual study. It is useful as a reproducible smoke campaign
showing that the compact envelope summary now groups by real month/hour/direction.

### Full-Year Top-1 QSTS

A full-year top-1 run was completed on `1-MV-rural--0-sw` after the in-place QSTS
candidate evaluator was added.

Output:

- `results/qsts_risk_summary_2026-05-13/qsts_top1_full_year_tol3/`.

Result:

| bus | evaluated hours | runtime seconds | power-flow calls | QSTS verdict | QSTS P90 MW | QSTS MWh | main constraint |
| ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| 2 | 8784 | 640.895 | 26716 | `no-go` | 0.000 | 120.977 | new high voltage at bus 15 |

This run meets the 15-minute target for top-1 annual validation, but it exposes the
central decision issue: P90 MW can be zero while expected curtailed energy is material.
The next implementation tranche therefore adds tail-risk diagnostics rather than
prioritizing C/Rust migration.

## Observed Strengths

The current MVP is now stronger than the original static screening prototype:

- static single-bus assessment and multi-bus screening work through the CLI;
- screening results are discriminating at 5 MW on the rural MV SimBench network;
- constraint aggregation now groups recurring constraints by element and metric rather
  than splitting by exact violation value;
- QSTS uses SimBench time-series profiles and pandapower power-flow replay;
- QSTS outputs distinguish raw binding constraints from incremental candidate-caused
  constraints;
- pre-existing benchmark-network violations no longer automatically force candidate
  curtailment;
- QSTS verdicts now depend on explicit P90 curtailment tolerance;
- QSTS verdicts can now require both explicit P90 curtailed MW and expected curtailed MWh
  tolerances;
- QSTS bounded annual campaigns can use stratified sampling instead of fixed-step weekly
  sampling, avoiding the artifact where all samples fall in the same time block;
- QSTS baseline states are cached across buses in a run, reducing repeated no-candidate
  power-flow work;
- QSTS runs can be bounded with `--start-hour`, `--duration-hours`, and
  `--sample-every-n-hours`;
- QSTS exports `investor_decision.csv` as a compact machine-readable decision table;
- QSTS exports detailed, compact, and contractual-envelope views;
- QSTS exports an investor-facing Markdown memo separate from the technical summary;
- QSTS records a run manifest with request, settings, generated outputs, environment, and
  git metadata;
- QSTS records performance counters and uses an in-place QSTS candidate evaluator to avoid
  repeated full network deep-copies during hourly candidate dispatch checks;
- QSTS investor memos now include a simple, explicit economics proxy;
- QSTS sweep runs aggregate sensitivity scenarios while preserving each scenario's full
  output bundle;
- QSTS summaries now include baseline diagnostics, runtime constraint settings, and
  envelope comparison and investor decision tables.

## Observed Weaknesses

### QSTS Sampling Can Miss Rare Annual Risk

The stratified top-3 run can classify a candidate as `go` while the full-year top-1
run classifies the same top bus as `no-go` because rare curtailed-energy events appear
outside the sample. Sampling is useful for iteration, but it must now be calibrated
against annual reference runs.

### Static And QSTS Curtailment Are Not Equivalent

The static custom-envelope proxy and the QSTS replay measure different things. Static
screening is useful for ranking, but QSTS is the higher-evidence validation layer.

For example, bus 21 has static P90 curtailment of 0.273 MW, but QSTS P90 curtailment
of 2.098 MW in the first 24-hour validation window.

### QSTS Runtime Is Usable For Top-1 But Still Costly For Campaigns

The full-year top-1 benchmark finished in 657 seconds. This is acceptable for a
reference run, but top-3 or sweep campaigns still need careful `top_n`, forced
`--bus-ids`, sampling calibration, and runtime reporting.

### The Economic Layer Is Still Proxy-Based

The current economic comparison uses configurable proxy values. It is adequate for
pre-feasibility experiments, but it is not yet a bankable valuation model.

### Contractual Envelope Is Conservative But Still V1

The contractual envelope now compresses QSTS feasible MW into RTE-inspired seasons and
time blocks using P10 allowed MW. It is more investment-ready than raw hourly rows, but it
does not yet optimize tariff-like periods, solve an OPF, or validate against operator-grade
study assumptions.

## Current Interpretation

The project is now past a simple static hosting-capacity demonstrator. It has a
working bridge from:

1. static screening;
2. candidate ranking;
3. baseline-aware QSTS validation;
4. user-defined QSTS curtailment tolerance;
5. revised `go`, `no-go`, or `go-with-conditions` decision;
6. QSTS-derived hourly, compact, and contractual flexible-envelope exports;
7. tail-risk diagnostics explaining verdict drivers beyond P90 alone.

The most important product/science insight is that the acceptable connection decision
depends on both the investor's tolerance for QSTS P90 curtailed MW and the expected
curtailed MWh. P90 alone is not sufficient for rare but material events.

Decision confidence is now explicit in QSTS outputs through `validation_level`,
`decision_confidence`, and `recommended_next_action`. The policy is documented in
`docs/decision-policy.md`: screening and short QSTS remain triage layers, stratified
QSTS is pre-demo evidence, and full-year QSTS is the MVP investor reference.

## Recommended Next Implementation Scope

The next implementation step should harden the decision layer:

1. Use `qsts_risk_summary.csv` to explain `go`, `go-with-conditions`, and `no-go`
   verdict drivers.
2. Calibrate stratified and sampled sweeps against full-year top-1 reference runs.
3. Use `--bus-ids` to run controlled validation cases under one tolerance policy.
4. Add sensitivity runs over:
   - requested MW;
   - QSTS P90 tolerance;
   - QSTS expected MWh tolerance;
   - voltage limit;
   - waiting-cost and curtailment-penalty assumptions.
5. Add stronger validation cases with one clear `go`, one `go-with-conditions`, and
   one `no-go` under the same tolerance policy.

## Immediate Corrections

Before larger campaigns, the following corrections should be made:

1. Validate whether the default QSTS expected-MWh tolerance should remain 0 MWh or use
   a product default for pre-feasibility campaigns.
2. Validate whether P10 allowed MW is the right default contractual value versus minimum
   or P25 allowed MW.
3. Benchmark whether the QSTS investor memo is sufficient for a first external demo.
4. Use `qsts_performance.json` to decide whether the next optimization should be
   pandapower recycling, parallelization, or a compiled backend investigation.

## Current Decision

Proceed next with decision robustness: risk-summary outputs, sampling calibration, and
controlled annual validation cases.

Do not move to OPF or advanced dynamic operating envelope optimization until the
QSTS-derived envelope is reproducible, summarized clearly, compared against the
static proxy and RTE-inspired gabarits, and converted into a compact contract-like
operating schedule.

## Canonical Investor Demo Run

Date: 2026-05-18

The first 90-day-plan tranche creates a reproducible investor-demo bundle:

- screening output: `results/demo_investor_2026-05-18/screen_5mw/`;
- representative QSTS output:
  `results/demo_investor_2026-05-18/qsts_representative_stratified_tol3_mwh60/`;
- full-year top-1 QSTS calibration:
  `results/demo_investor_2026-05-18/qsts_bus2_full_year_tol3_mwh60/`;
- demo walkthrough: `docs/demo-script.md`;
- metric guide: `docs/interpretation-guide.md`.

Representative stratified QSTS result:

| bus | QSTS verdict | QSTS P90 MW | QSTS MWh | driver |
| ---: | --- | ---: | ---: | --- |
| 2 | `go` | 0.000 | 0.000 | no curtailment |
| 21 | `no-go` | 2.148 | 165.703 | expected MWh exceeds tolerance |
| 24 | `no-go` | 2.617 | 206.094 | expected MWh exceeds tolerance |

This run makes the central decision lesson explicit: P90 curtailed MW can remain below
the configured tolerance while expected curtailed MWh still rejects the project. The
investor-facing verdict therefore needs both power-risk and energy-risk thresholds.

Full-year top-1 calibration result:

| bus | QSTS verdict | QSTS P90 MW | QSTS MWh | curtailment hours | runtime seconds |
| ---: | --- | ---: | ---: | ---: | ---: |
| 2 | `no-go` | 0.000 | 120.977 | 52 | 659.328 |

The full-year result flips bus 2 from stratified `go` to annual `no-go`, driven by
expected MWh rather than P90 MW. This confirms that stratified QSTS is useful for fast
triage, but must be calibrated against annual runs before an investor-grade conclusion.

## Full-Year Multi-Bus Calibration

Date: 2026-05-18

Calibration bundle:

- output root: `results/full_year_calibration_2026-05-18/`;
- bus 21 full-year QSTS:
  `results/full_year_calibration_2026-05-18/qsts_bus21_full_year_tol3_mwh60/`;
- validation matrix:
  `results/full_year_calibration_2026-05-18/validation_matrix/`.

The comparison matrix uses:

- screening: `results/demo_investor_2026-05-18/screen_5mw/screening.csv`;
- short QSTS:
  `results/decision_policy_2026-05-18/qsts_24h_buses_2_21_24_tol3_mwh60/qsts_results.csv`;
- stratified QSTS:
  `results/decision_policy_2026-05-18/qsts_stratified_buses_2_21_24_tol3_mwh60/qsts_results.csv`;
- full-year QSTS for bus 2 and bus 21.

Calibration result:

| bus | screening | short | stratified | full-year | final decision | calibration status |
| ---: | --- | --- | --- | --- | --- | --- |
| 2 | `go` | `go` | `go` | `no-go` | `no-go` | `false_positive_stratified` |
| 21 | `no-go` | `go-with-conditions` | `no-go` | `no-go` | `no-go` | `changed_after_full_year` |
| 24 | `no-go` | `go-with-conditions` | `no-go` | not run | `requires_full_year_validation` | `requires_full_year_validation` |

Bus 21 confirms that a constrained case can become materially stronger under annual
validation: expected curtailed energy is 17,759.024 MWh in the full-year run, with
P90 curtailed power still below the 3 MW tolerance. Bus 24 remains the next optional
annual run if more calibration depth is needed.
