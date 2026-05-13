# Benchmark Log

This log records reproducible benchmark bundles used to judge MVP progress. Generated
results stay under `results/`; this file keeps only the evidence needed to interpret the
state of the project.

## 2026-05-13 - QSTS Performance And Annual Top-1

Network: `1-MV-rural--0-sw`

Screening source: `results/qsts_performance_2026-05-13/screen_5mw/screening.csv`

### Stratified Top-3 Smoke

Output:

- `results/qsts_performance_2026-05-13/qsts_top3_stratified_tol3/`

Purpose:

- verify bounded annual sampling;
- verify QSTS output bundle generation;
- keep an interactive smoke path for future changes.

### QSTS Sweep Smoke

Output:

- `results/qsts_performance_2026-05-13/sweep_smoke/`

Purpose:

- verify `qsts-sweep` scenario generation;
- verify per-scenario output bundles;
- verify aggregate sensitivity CSV and Markdown summary.

### Full-Year Top-1 Reference

Output:

- `results/qsts_risk_summary_2026-05-13/qsts_top1_full_year_tol3/`

Key metrics:

| metric | value |
| --- | ---: |
| runtime_seconds | 640.895 |
| power_flow_calls | 26716 |
| baseline_power_flow_calls | 8784 |
| candidate_power_flow_calls | 17932 |
| binary_search_count | 52 |
| evaluated_time_steps | 8784 |
| evaluated_buses | 1 |

Decision result:

| bus | verdict | firm MW | conditional MW | P90 MW | expected MWh | dominant constraint |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 2 | `no-go` | 5.000 | 5.000 | 0.000 | 120.977 | new high voltage at bus 15 |

Risk summary:

| bus | verdict driver | tail risk | curtailment hours | max MW | max event MWh |
| ---: | --- | --- | ---: | ---: | ---: |
| 2 | `mwh_exceeds_tolerance` | true | 52 | 5.000 | 5.000 |

Interpretation:

The run meets the 15-minute target for an annual top-1 reference, but it shows that
`P90 MW = 0` can still hide material expected curtailed energy. This is why the next
decision layer tracks verdict drivers, P95/P99/max curtailment, consecutive curtailment
events, and a tail-risk flag.
