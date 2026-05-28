# Modeling assumptions

This document records the explicit assumptions behind the V1 BESS pre-feasibility
engine. These assumptions are intentionally conservative and must be revisited before
using the tool for bankable studies.

## Scope

- V1 assesses BESS pre-feasibility only.
- The output is a buyer-side investment memo, not an official grid-connection study.
- The first production logic lives in `src/`; notebooks are exploratory only.

## Power-system model

- The main implementation layer is pandapower for AC steady-state power flow.
- SimBench is the first benchmark source for reproducible network experiments.
- The built-in `toy` network is only a deterministic smoke-test network and is not a
  scientific benchmark.
- The default voltage band is 0.95-1.05 pu.
- The default line and transformer loading limit is 100%.
- The MVP does not model short-circuit duty, protection, dynamic stability, N-1
  security, harmonic limits, or official operator planning criteria.

## BESS representation

- A BESS is tested as injection and withdrawal at the candidate bus.
- Injection is represented as positive active-power generation.
- Withdrawal is represented as positive active-power load.
- The BESS-lite sizing layer records requested MW, storage duration, nominal MWh,
  round-trip efficiency, and an SoC window for evidence traceability.
- BESS-lite is not a dispatch, degradation, revenue-stacking, reserve-market, outage, or
  bankable valuation model.
- Reactive power is set to zero in the first MVP unless a future study explicitly
  defines a power-factor or reactive-control assumption.
- The headline firm capacity is the minimum of firm injection and firm withdrawal,
  while the memo still reports both directional values.

## Firm and conditional capacity

- Firm capacity is estimated by binary search over requested MW and repeated
  steady-state power-flow checks.
- A candidate MW is infeasible when the power flow diverges, voltage leaves the
  default band, or any line/transformer exceeds the default loading limit.
- Conditional capacity is represented as a flexible operating envelope that may
  curtail operation during restricted or constrained hours.
- `conditional_capacity_mw` is the maximum accepted capacity up to the requested MW
  under the configured P90 curtailment tolerance and positive flexible-value proxy.
- `evaluated_conditional_mw` is the requested MW at which the memo's envelope,
  curtailment, and economic risk are evaluated. It can be higher than
  `conditional_capacity_mw` for a `no-go` case.
- The memo compares `firm-only`, both RTE-inspired gabarits, and a custom envelope at
  the evaluated MW before selecting the lowest-curtailment recommended envelope.
- Single-bus assessment memos use a simplified hourly curtailment proxy.
- QSTS validation replays SimBench time-varying operating points and checks BESS
  injection and withdrawal with repeated pandapower power flows.
- QSTS can use either regular interval sampling or stratified sampling. The V1 stratified
  sampling selects representative hours across months and the fixed contractual-envelope
  time blocks to avoid aliasing all samples into the same hour of day.
- QSTS verdicts are incremental against a no-candidate baseline. Pre-existing
  benchmark-network violations are reported in detail files but do not trigger
  curtailment unless the candidate creates a new violation or worsens an existing one.
- QSTS `go-with-conditions` requires the QSTS P90 curtailed MW to be within the
  user-configured `p90_curtailment_tolerance_mw` and QSTS expected curtailed MWh to
  be within `expected_curtailment_tolerance_mwh`; both default tolerances are 0.
- The QSTS contractual-envelope export is a compact investor-facing synthesis of the
  hourly QSTS-derived envelope. It groups by direction, RTE-inspired V1 season, and
  fixed time block, and uses P10 allowed MW as the recommended conservative contract
  value. This is a pre-feasibility synthesis, not an official RTE operating gabarit.
- QSTS results are a higher-evidence validation layer than the static proxy, but they
  remain benchmark results unless validated against operator study cases.
- QSTS output bundles include `investment_memo.md` for the investor-facing synthesis and
  `run_manifest.json` for reproducibility. The manifest records the request, constraint
  settings, generated artefacts, Python/platform metadata, package version, and git state.
- QSTS performance counters are diagnostic and include all baseline and candidate
  power-flow attempts made by the QSTS workflow. They are used to benchmark annual runs,
  not to certify network feasibility.
- QSTS investment-memo economics are proxy-based. They use explicit user-provided or
  default assumptions and must not be treated as a bankable valuation model.

## French V1 gabarits

The V1 includes two CRE/RTE-inspired ex-ante horo-seasonal calendars:

- injection gabarit: injection forbidden from 10:00 to 18:00, March through October;
- withdrawal gabarit: withdrawal forbidden from 07:00 to 13:00 and 17:00 to 21:00,
  November through March.

These calendars are modeled as half-open hourly intervals: 10:00 is restricted,
18:00 is not; 07:00 is restricted, 13:00 is not; 17:00 is restricted, 21:00 is not.

## Economics

- The economic layer uses configurable proxy values.
- EBITDA-at-risk is estimated as curtailed MWh multiplied by a curtailment penalty.
- Waiting value is estimated as requested MW multiplied by reinforcement wait years
  and a waiting-cost proxy.
- RTE eCO2mix market-price data is not assumed reusable for commercial pricing.
  Commercial pricing assumptions must use licensed data or user-provided proxies.

## Decision thresholds

- `go`: requested MW is within firm capacity and P90 curtailment is zero.
- `go-with-conditions`: requested MW is within conditional capacity, P90 curtailment
  is within user tolerance, and the flexible option has positive proxy value.
- `no-go`: all other cases.
- QSTS verdicts use the same labels but apply QSTS-specific tolerances: `go` requires
  zero QSTS P90 curtailed MW and zero expected curtailed MWh; `go-with-conditions`
  requires both configured QSTS P90 MW and expected MWh tolerances to be met.

## Remaining uncertainty

- SimBench networks are benchmarks and do not replace French operator models.
- France-specific validation requires public RTE context and, where possible,
  confidential operator data or validated study cases.
- QSTS validation improves the conditional-capacity method, but scientific claims beyond
  pre-feasibility still require sensitivity studies, additional networks, and comparison
  against official or operator-grade study assumptions.
