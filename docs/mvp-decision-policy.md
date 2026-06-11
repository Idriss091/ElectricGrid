# MVP Decision Policy

This document defines the default investor-facing decision policy for the VoltPath BESS
pre-feasibility MVP.

The default investor-facing policy is `standard`.

## Verdicts

`go`

No QSTS curtailment is observed for the requested MW at the evaluated validation level.

`go-with-conditions`

Curtailment is observed, but P90 curtailed MW ratio, curtailed-energy ratio, maximum
event duration, and maximum event MWh per MW are acceptable under the selected policy.
For BESS pre-feasibility, an event can exceed the comfort event-energy threshold and
still remain `go-with-conditions` when P90 risk, annual energy risk, and event duration
remain within policy and the event stays below the policy's conditional hard cap.

`resize-recommended`

The original requested MW fails the selected policy, but a lower tested MW passes the
selected policy.

`investigate-only`

Only the `aggressive` policy passes. This is not investor-grade evidence and requires
stronger economics, better data, or further study before commercial use.

`no-go`

The requested MW exceeds the selected policy, or no tested lower MW is acceptable.

## Standard Policy Thresholds

The `standard` policy is the default conservative investor-facing pre-feasibility
policy:

- p90_curtailment_ratio <= 10%
- curtailment_energy_ratio <= 1.0%
- max_event_hours <= 12
- comfort max_event_mwh_per_mw <= 1.0
- conditional hard cap max_event_mwh_per_mw <= 2.0

## Status

These thresholds are VoltPath pre-feasibility policy assumptions. They are not RTE, Enedis, CRE, or official operator thresholds.

The comfort event-energy threshold is a warning threshold, not an automatic rejection
threshold. The conditional hard cap is the standard-policy rejection threshold when
P90, annual energy, and event duration remain acceptable.

## Calibration Needed

The thresholds must be calibrated with more full-year QSTS runs and pilot feedback.

The current calibration priority is:

- compare screening, short QSTS, stratified QSTS, and full-year QSTS;
- measure false positives and false negatives by policy;
- test requested MW values across several buses and networks;
- verify whether `standard` is too strict or too permissive for BESS developers and
  investors.
