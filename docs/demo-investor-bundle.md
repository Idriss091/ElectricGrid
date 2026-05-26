# Investor Bundle README

Use this file as the README template for the canonical BESS investor demo bundle.

## Scenario

- Network: `1-MV-rural--0-sw`
- Asset: BESS
- Requested capacity: 5 MW
- Representative buses: 2, 21, 24
- QSTS P90 curtailment tolerance: 3 MW
- QSTS expected curtailed-energy tolerance: 60 MWh
- Constraint settings: 0.95-1.05 pu voltage band and 100% thermal loading limit

## Required Files

- `screening_summary.md`
- `screening.csv`
- `qsts_results.csv`
- `qsts_risk_summary.csv`
- `investment_memo.md`
- `contractual_envelope.csv`
- `static_vs_qsts_comparison.csv`
- `validation_matrix.md`
- `run_manifest.json`
- `qsts_performance.json`

## Interpretation

The bundle is a buyer-side pre-feasibility aid. It does not replace an official
RTE, Enedis, or operator connection study.

The contractual envelope is an approximation pre-feasibility output inspired by
RTE/CRE storage gabarit vocabulary. It is not a PTF and not an official network
operator offer.

Use `validation_matrix.md` as the primary calibration artifact. A full-year QSTS
verdict is the MVP investor reference layer when available. Screening, short QSTS, and
stratified QSTS remain triage or pre-demo evidence.

Use `qsts-resize` when the requested MW is rejected. The product decision
`resize-recommended` means a lower tested MW is acceptable under the selected
decision-frontier policy.
