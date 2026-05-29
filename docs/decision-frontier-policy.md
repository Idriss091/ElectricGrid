# Decision frontier policy

## Purpose

Thesegrid should not use a single hard-coded curtailment threshold as if it were a
universal truth.

Flexible connections are commercial and contractual decisions. The same full-year QSTS
result can be unacceptable for a conservative investor and still worth investigating for
a developer with a high tolerance for flexible operation.

The decision frontier is therefore a sensitivity layer over full-year evidence.

## Metrics

The V2 decision frontier uses:

- `p90_mw`: 90th percentile curtailed MW;
- `p90_curtailment_ratio`: `p90_mw / requested_mw`;
- `weighted_curtailment_mwh`: decision-weighted curtailed MWh;
- `curtailment_energy_ratio`: `weighted_curtailment_mwh / (requested_mw * 8760)`;
- `max_event_hours`: longest contiguous curtailment event;
- `max_event_mwh_per_mw`: longest event MWh normalized by requested MW.

The ratios are important because absolute MW and MWh thresholds mean different things
for a 2 MW project and a 20 MW project.

## Policies

| policy | max P90 ratio | max energy ratio | max event hours | max event MWh/MW | intended interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| strict | 5% | 0.25% | 6 | 0.25 | quasi-firm investor case |
| standard | 10% | 1.0% | 12 | 1.0 | conservative pre-feasibility |
| flexible | 25% | 2.5% | 48 | 2.5 | explicit flexible-connection appetite |
| aggressive | 40% | 5.0% | 96 | 5.0 | speculative case requiring strong economics |

These thresholds are V2 product-policy assumptions, not regulatory or operator
thresholds.

## Classification

For each policy:

- `go`: no P90, energy, or event curtailment is observed.
- `go-with-conditions`: P90 ratio, energy ratio, and event risk are all within the
  selected strict, standard, or flexible policy.
- `investigate-only`: the aggressive policy is satisfied, but the case exceeds the
  flexible policy. This is not an investor-grade go verdict.
- `no-go`: at least one policy limit is exceeded.

The original QSTS verdict remains available. The frontier table is a sensitivity view
used to explain where the decision boundary sits.

## Current Campaign Lesson

The current calibration campaign should evaluate each candidate against ratio-based
policy thresholds, not fixed absolute MW/MWh values. A candidate can pass a P90 power
threshold while still failing the annual energy or maximum-event thresholds.

This supports the product thesis: P90 MW alone is not enough. The investor decision also
needs annual energy, frequency of curtailment, and economics.
