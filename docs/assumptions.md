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
- Until validated annual QSTS profiles are added, conditional curtailment is a
  simplified hourly risk proxy and must be labelled as such in the memo.

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

## Remaining uncertainty

- SimBench networks are benchmarks and do not replace French operator models.
- France-specific validation requires public RTE context and, where possible,
  confidential operator data or validated study cases.
- The conditional-capacity method needs QSTS validation before scientific claims are
  made beyond pre-feasibility.
