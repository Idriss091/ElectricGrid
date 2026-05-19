# QSTS worker model

Full-year QSTS is the MVP investor reference layer, but it is too slow for a synchronous
SaaS request path. The next production step is to isolate QSTS work by bus and scenario.

## Unit of work

The parallelization unit is `bus`.

Each worker receives:

- network code;
- screening CSV path;
- one bus id;
- requested MW;
- QSTS sampling mode;
- constraint settings;
- curtailment tolerances;
- economic proxy settings;
- output directory.

Each worker writes a standard QSTS bundle for that bus. A coordinator can then merge
`qsts_results.csv`, `investor_decision.csv`, `qsts_risk_summary.csv`,
`contractual_envelope.csv`, `static_vs_qsts_comparison.csv`, and the validation matrix.

## Required metrics

Every run must expose:

- `runtime_seconds`;
- `power_flow_calls`;
- `baseline_power_flow_calls`;
- `candidate_power_flow_calls`;
- `binary_search_count`;
- `baseline_cache_hits`;
- `baseline_cache_misses`;
- `evaluated_time_steps`;
- `evaluated_buses`;
- `evaluated_bus_hours`;
- `power_flow_calls_per_bus_hour`;
- `runtime_seconds_per_bus_hour`;
- `parallelization_unit`.

## Failure handling

A failed bus should not invalidate completed bus outputs. The future coordinator should
write a manifest row for failed buses with the exception message, command, scenario id,
and git state.
