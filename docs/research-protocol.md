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
6. Estimate curtailment hours, MWh, P50, and P90.
7. Compare connect-now-flexible against wait-for-reinforcement using configurable
   economic proxies.
8. Emit a machine-generated memo into `results/<run_id>/memo.md`.

## Product outputs

The product MVP must emit:

- maximum firm injection and withdrawal capacity;
- headline firm capacity;
- conditional capacity;
- recommended envelope;
- binding constraints;
- expected curtailment;
- EBITDA-at-risk proxy;
- go / no-go / go-with-conditions recommendation.

## Scientific outputs

The paper should use the same experiment outputs to build:

- a formal definition of flexible interconnection envelope synthesis;
- a benchmark study over multiple buses and networks;
- sensitivity analysis over curtailment tolerance, waiting time, and economic proxies;
- a limitations section separating pre-feasibility from official network studies.

## Reproducibility rules

- Every run must record network code, bus id, requested MW, economic assumptions, and
  constraint settings.
- Raw sources stay in `papers/` or `Scientific-Pappers/`.
- Code stays in `src/`.
- Tests stay in `tests/`.
- Generated memos and experiment outputs stay in `results/`.
