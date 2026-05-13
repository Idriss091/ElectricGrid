# Current State and QSTS Next Steps

Date: 2026-05-09

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
thesegrid qsts --network <network_code> --screening-csv <screening_csv> --requested-mw <mw> --top-n <n> --start-hour <h> --duration-hours <h> --sample-every-n-hours <n> --stratified-sample --voltage-min-pu <pu> --voltage-max-pu <pu> --max-loading-percent <percent> --p90-curtailment-tolerance-mw <mw> --expected-curtailment-tolerance-mwh <mwh> --progress-every-n-hours <n> --storage-duration-hours <h> --capex-eur-per-kw <eur> --fixed-opex-eur-per-kw-year <eur> --gross-revenue-eur-per-mw-year <eur> --curtailment-penalty-eur-per-mwh <eur> --reinforcement-wait-years <years> --discount-rate <rate> --output <output_dir>
thesegrid qsts-sweep --config <sweep_json> --output <output_dir>
```

## Verification Performed

The latest automated checks passed after the envelope implementation:

- `python -m pytest -q`: 49 passed, 1 skipped;
- `.venv/bin/python -m pytest -q`: 50 passed;
- `python -m ruff check .`: passed.

The `.venv` run includes SimBench-dependent tests.

## Latest Audit Runs

Latest generated outputs are under:

- `results/qsts_envelope_2026-05-09/`.

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

### QSTS Is Still A Short-Window Validation In The Audit

The latest QSTS audit used a 24-hour window, not the full year. This is enough to
validate behavior and expose methodological issues, but it is not yet a scientific
annual result.

### Static And QSTS Curtailment Are Not Equivalent

The static custom-envelope proxy and the QSTS replay measure different things. Static
screening is useful for ranking, but QSTS is the higher-evidence validation layer.

For example, bus 21 has static P90 curtailment of 0.273 MW, but QSTS P90 curtailment
of 2.098 MW in the first 24-hour validation window.

### QSTS Runtime Still Needs More Performance Work

The bounded 24-hour top-3 QSTS runs are manageable, and the sampled annual run is
usable. Full annual QSTS with binary search per hour, direction, and bus will still
be expensive. Annual campaigns should use careful `top_n`, time-window controls,
caching, and possibly parallelization.

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
6. QSTS-derived hourly, compact, and contractual flexible-envelope exports.

The most important product/science insight is that the acceptable connection decision
depends on the investor's tolerance for QSTS P90 curtailed MW and on whether the
candidate is judged by a static proxy or an hourly QSTS-derived envelope.

## Recommended Next Implementation Scope

The next implementation step should harden the new contractual-envelope layer:

1. Benchmark contractual-envelope behavior on full annual top-1 and top-3 QSTS runs.
2. Add sensitivity runs over contractual conservatism, including P10, P25, minimum, and P50
   allowed MW.
3. Add annual sensitivity runs over:
   - requested MW;
   - QSTS P90 tolerance;
   - QSTS expected MWh tolerance;
   - voltage limit;
   - waiting-cost and curtailment-penalty assumptions.
4. Add runtime controls:
   - cache baseline snapshots;
   - cache profile-loaded networks;
   - optionally parallelize across buses.
5. Add stronger validation cases with one clear `go`, one `go-with-conditions`, and
   one `no-go` under the same tolerance policy.

## Immediate Corrections

Before larger campaigns, the following corrections should be made:

1. Validate whether the default QSTS expected-MWh tolerance should remain 0 MWh or use
   a product default for pre-feasibility campaigns.
2. Validate whether P10 allowed MW is the right default contractual value versus minimum
   or P25 allowed MW.
3. Benchmark whether the QSTS investor memo is sufficient for a first external demo.
4. Benchmark a full annual top-1 run before attempting full annual top-10.
5. Use `qsts_performance.json` to decide whether the next optimization should be
   pandapower recycling, parallelization, or a compiled backend investigation.

## Current Decision

Proceed next with contractual-envelope validation and performance hardening.

Do not move to OPF or advanced dynamic operating envelope optimization until the
QSTS-derived envelope is reproducible, summarized clearly, compared against the
static proxy and RTE-inspired gabarits, and converted into a compact contract-like
operating schedule.
