# Current State and QSTS Next Steps

Date: 2026-05-09

## Purpose

This document records the current state of the BESS pre-feasibility MVP after the
latest audit, what was tested, what works, what remains weak, and why the next
implementation step should be QSTS validation on the top-ranked buses.

The project remains a buyer-side decision engine for flexible grid-connection
pre-feasibility. It does not replace an official grid-connection study.

## Current Product State

The current MVP can:

- assess one candidate BESS connection bus;
- estimate firm injection and withdrawal capacity;
- estimate a maximum accepted conditional capacity up to the requested MW;
- compare firm-only, RTE-inspired gabarits, and a custom envelope;
- estimate curtailment risk with P50/P90 metrics;
- estimate a configurable economic proxy for connecting now versus waiting;
- return a `go`, `go-with-conditions`, or `no-go` verdict;
- screen multiple MV candidate buses and rank them in a CSV and Markdown summary.

The main user-facing commands are:

```bash
thesegrid assess --network <network_code> --bus <bus_id> --requested-mw <mw> --output <memo_path>
thesegrid screen --network <network_code> --requested-mw <mw> --output <output_dir>
```

## Verification Performed

The codebase passed the automated checks:

- `python -m pytest -q`: 24 passed, 1 skipped;
- `.venv/bin/python -m pytest -q`: 25 passed;
- `python -m ruff check .`: passed.

The repository was clean before generating the audit results.

## Audit Runs

### Toy Network

The toy network was used to verify that all verdict classes can be produced.

| Case | Result |
| --- | --- |
| `toy`, bus 1, 4 MW | `go` |
| `toy`, bus 1, 5.5 MW, P90 tolerance 1 MW | `go-with-conditions` |
| `toy`, bus 1, 8 MW, P90 tolerance 1 MW | `no-go` |
| `toy` screening, 5.5 MW | CSV and Markdown summary generated |

These runs confirm that the current decision logic is internally coherent.

### SimBench Network

The SimBench network `1-MV-rural--0-sw` was used for a more realistic screening
smoke test.

At 0.5 MW:

- 95 candidate buses were evaluated;
- all 95 returned `go`;
- this case is technically useful as a smoke test, but not discriminating enough for
  product demonstration or research results.

At 5 MW:

- 95 candidate buses were evaluated;
- 44 returned `go`;
- 14 returned `go-with-conditions`;
- 37 returned `no-go`.

This 5 MW run is the current best audit case because it produces meaningful ranking
differences and exposes voltage and thermal constraints.

Important generated outputs:

- `results/audit_simbench_screen_5mw/screening_summary.md`;
- `results/audit_simbench_screen_5mw/screening.csv`;
- `results/audit_simbench_bus21_conditional/memo.md`;
- `results/audit_simbench_bus24_nogo/memo.md`.

## Observed Strengths

The MVP is technically healthy and already useful for pre-feasibility screening:

- tests and lint pass;
- single-bus assessment and multi-bus screening work through the CLI;
- SimBench integration works in the virtual environment;
- the screening becomes informative when the requested MW stresses the network;
- the memo clearly reports assumptions, constraints, curtailment, economics, and
  remaining scientific uncertainty;
- the CSV output is suitable for analysis and ranking.

## Observed Weaknesses

The main limitations are methodological rather than basic software bugs.

### Conditional Curtailment Is Still A Proxy

When requested MW is above firm capacity, the current custom envelope often curtails
a constant MW gap across all 8760 hours. This is deterministic and easy to explain,
but it is not yet a real hourly network simulation.

This is acceptable for MVP pre-feasibility, but too weak for a scientific claim about
probabilistic or dynamic envelope synthesis.

### Custom Envelope Is Too Favorable

The custom envelope usually wins because it only trims the requested MW down to the
firm directional limit. This makes it look better than fixed RTE-inspired gabarits,
but it does not yet prove that this envelope is operationally valid across hourly
network states.

QSTS should validate whether a custom envelope remains feasible when load and
generation profiles vary over time.

### Low-MW Screening Is Not Discriminating

The 0.5 MW SimBench screening returned all buses as `go`. This is useful as a smoke
test but not useful for demos, ranking, or paper tables.

For the current SimBench rural MV network, 5 MW is a better stress-test value.

### Constraint Aggregation Needs Improvement

The screening summary currently aggregates frequent binding constraints by full
description, including the exact violation value. This splits the same constraint
into multiple rows when the value changes slightly.

The aggregation should instead group by:

- element type;
- element id;
- metric.

The summary can then report count, max violation, and representative element name.

### Screening Performance Needs Guardrails

The 5 MW SimBench screening over 95 buses took roughly tens of seconds. This is
acceptable for an audit run, but it will become painful for larger experiments.

Before larger campaigns, the CLI should support:

- limiting the number of evaluated buses;
- showing progress;
- optionally caching or parallelizing repeated assessments.

## Why QSTS Is The Right Next Step

QSTS validation is the next best bridge between the product and the scientific paper.

For the product, it makes the memo more credible because curtailment risk is computed
from hourly operating states rather than a simplified annual proxy.

For the paper, it moves the contribution from static hosting-capacity screening
toward flexible interconnection envelope validation under time-varying network
conditions.

OPF or full dynamic operating envelope optimization should come later. QSTS provides
the baseline needed before optimizing envelopes.

## Recommended Next Implementation Scope

The next implementation should add a QSTS Top-N workflow:

1. Run or load a screening result.
2. Select the top N candidate buses.
3. Load SimBench time-series profiles for the selected network.
4. For each selected bus and requested MW, replay hourly operating points.
5. Add BESS injection and withdrawal scenarios.
6. Run pandapower power flow per time step.
7. Record voltage, line, transformer, and convergence violations.
8. Compute hourly feasible MW, curtailed MW, expected curtailment MWh, P50/P90, and
   recurring constraints.
9. Emit:
   - `qsts_results.csv`;
   - `qsts_summary.md`;
   - optional per-bus detail CSVs.

The first implementation should stay narrow:

- BESS only;
- SimBench only;
- top N buses only;
- no OPF yet;
- no UI;
- no claim of official grid-study replacement.

## Immediate Corrections Before Or During QSTS

The following corrections should be included in or just before the QSTS step:

1. Add `--max-buses` to screening so experiments can be bounded.
2. Improve frequent-constraint aggregation in screening summaries.
3. Add timing/progress visibility for screening and QSTS runs.
4. Make the QSTS output explicit about whether results come from proxy logic or
   actual hourly power-flow validation.
5. Document the remaining limits in `docs/assumptions.md` after QSTS is implemented.

## Current Decision

Proceed next with QSTS validation on top-ranked buses from the 5 MW SimBench
screening.

This should be treated as the next research/product milestone before any OPF or
more advanced dynamic operating envelope optimization.
