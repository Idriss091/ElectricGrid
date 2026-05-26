# Decision frontier policy

## Purpose

Thesegrid should not use a single hard-coded curtailment threshold as if it were a
universal truth.

Flexible connections are commercial and contractual decisions. The same full-year QSTS
result can be unacceptable for a conservative investor and still worth investigating for
a developer with a high tolerance for flexible operation.

The decision frontier is therefore a sensitivity layer over full-year evidence.

## Metrics

The V1 decision frontier uses:

- `p90_mw`: 90th percentile curtailed MW;
- `expected_mwh`: annual curtailed MWh across the evaluated QSTS period;
- `curtailment_energy_ratio`: `expected_mwh / (requested_mw * 8760)`.

The ratio is important because an absolute MWh threshold means different things for a
2 MW project and a 20 MW project.

## Policies

| policy | max P90 MW | max MWh | max energy ratio | intended interpretation |
| --- | ---: | ---: | ---: | --- |
| strict | 0.5 | 60 | 0.5% | quasi-firm investor case |
| standard | 1.0 | 120 | 1.0% | conservative pre-feasibility |
| flexible | 3.0 | 500 | 2.0% | explicit flexible-connection appetite |
| aggressive | 3.0 | 1000 | 5.0% | speculative case requiring strong economics |

These thresholds are V1 policy assumptions, not regulatory or operator thresholds.

## Classification

For each policy:

- `go`: P90 MW is zero and expected curtailed MWh is zero.
- `go-with-conditions`: P90 MW, expected MWh, and energy ratio are all within the
  selected policy.
- `no-go`: at least one policy limit is exceeded.

The original QSTS verdict remains available. The frontier table is a sensitivity view
used to explain where the decision boundary sits.

## Current lesson from the demo

Bus 21 at 3 MW has a low P90 curtailment value, but the annual curtailed MWh is high
enough to fail strict, standard, and flexible policies.

Bus 24 at 3 MW is structurally constrained in the full-year run and fails all practical
policies.

This supports the product thesis: P90 MW alone is not enough. The investor decision also
needs annual energy, frequency of curtailment, and economics.
