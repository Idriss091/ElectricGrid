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
6. Estimate curtailment hours, MWh, P50, and P90 at the evaluated requested MW.
7. Search the maximum conditional MW accepted under curtailment tolerance and positive
   flexible-value proxy.
8. Compare connect-now-flexible against wait-for-reinforcement using configurable
   economic proxies.
9. Emit a machine-generated memo into `results/<run_id>/memo.md`.

## Multi-bus screening experiment

The first repeatable product/science experiment is a multi-bus BESS screening run:

1. Select one SimBench network code.
2. Select one requested BESS MW value.
3. Select active MV candidate buses and exclude slack or external-grid buses.
4. Run the mono-bus assessment for each candidate bus.
5. Rank buses by investment decision quality:
   verdict, flexible value delta, conditional capacity, P90 curtailment, then firm
   capacity.
6. Write `screening.csv` for analysis and `screening_summary.md` for the product-style
   decision narrative.

This screening is the bridge between the commercial site-selection workflow and the
paper's benchmark tables. It remains a pre-feasibility proxy until time-series/QSTS
validation is added for the best-ranked buses.

## Product outputs

The product MVP must emit:

- maximum firm injection and withdrawal capacity;
- headline firm capacity;
- maximum conditional capacity accepted up to the requested MW;
- evaluated conditional MW used for the risk and economic estimate;
- recommended envelope;
- envelope comparison across firm-only, RTE-inspired, and custom envelopes;
- binding constraints;
- expected curtailment;
- EBITDA-at-risk proxy;
- go / no-go / go-with-conditions recommendation.

For multi-bus screening, the product also emits:

- ranked candidate bus table;
- top-10 decision summary;
- verdict distribution;
- most frequent binding constraints.

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
