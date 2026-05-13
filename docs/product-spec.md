# Product specification

## Users

Primary V1 users:

- BESS developers;
- grid-connection consultants;
- energy/site-selection teams for large loads.

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
- Envelope comparison across firm-only, RTE-inspired, and custom envelopes
- Expected curtailment hours
- P50/P90 curtailment estimate
- EBITDA-at-risk estimate
- Go / no-go / go-with-conditions recommendation
- Automated investment memo
- QSTS bundle with `investment_memo.md`, `run_manifest.json`, `qsts_performance.json`,
  `static_vs_qsts_comparison.csv`, and contractual-envelope CSVs
- QSTS sensitivity sweep outputs for comparing verdict thresholds across requested MW,
  curtailment tolerance, and voltage assumptions

## V1 limitation

The V1 focuses on pre-feasibility.
It does not replace the official network operator connection study.
