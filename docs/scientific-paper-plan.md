# Scientific paper plan

## Working title

Probabilistic synthesis of flexible interconnection envelopes for BESS and large loads under network and economic uncertainty.

## Core research question

How can network hosting capacity be converted into a flexible contractual and economic connection proposal under uncertainty?

## Method blocks

1. Probabilistic pre-screening of candidate connection points.
2. Co-optimization of firm capacity, conditional capacity, and flexible envelope.
3. Time-series validation using synthetic or real yearly profiles.
4. Techno-economic translation into curtailment risk and investment value.
5. Sensitivity analysis over curtailment appetite, contractual-envelope conservatism,
   voltage limits, and economic assumptions.

## Expected contribution

The contribution is not just computing hosting capacity.
The contribution is transforming hosting capacity into:

- firm MW;
- conditional MW;
- operational envelope;
- curtailment risk;
- economic decision.

## Experimental protocol for the MVP paper

1. Use SimBench networks as the reproducible benchmark layer.
2. Screen candidate buses and compute directional BESS firm capacity with pandapower.
3. Generate conditional envelopes using explicit horo-seasonal gabarits and custom
   hourly envelopes.
4. Estimate curtailment risk as expected hours, expected MWh, P50, and P90.
5. Translate curtailment into EBITDA-at-risk and compare against a wait-for-reinforcement
   proxy.
6. Validate top candidates with QSTS, export a static-vs-QSTS comparison, and record
   runtime/power-flow counts for reproducibility.
7. Report the decision as go, no-go, or go-with-conditions.

## Baseline claims to avoid

- Do not claim that the method replaces official grid-connection studies.
- Do not claim French bankability from SimBench alone.
- Do not claim dynamic validation until QSTS or equivalent annual time-series studies
  have been run.
- Do not use RTE market-price data commercially without a suitable license.

## Initial journal strategy

- arXiv first to establish the method and terminology.
- Applied Energy as the ambitious target if the probabilistic and economic contribution
  is strong enough.
- Sustainable Energy, Grids and Networks or Electric Power Systems Research as more
  direct power-system alternatives.
