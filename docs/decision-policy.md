# Decision Policy

This document defines how BESS flexible-connection verdicts should be read in the MVP.
The policy is intentionally conservative because the product is a buyer-side
pre-feasibility aid, not an official grid-connection study.

## Validation Levels

| level | use | investor meaning |
| --- | --- | --- |
| `screening_only` | Static steady-state ranking | Fast triage only. Do not treat as final. |
| `qsts_short` | Bounded QSTS window, for example 24 hours | Smoke validation. Use to catch obvious issues. |
| `qsts_stratified` | Representative annual samples across months and time blocks | Pre-demo evidence. Useful for comparing sites. |
| `qsts_full_year` | Full annual QSTS profile replay | MVP investor reference. Use before a robust conclusion. |

QSTS outputs now include:

- `validation_level`;
- `decision_confidence`;
- `recommended_next_action`.

## Evidence Funnel

Do not run every validation layer on every bus. The MVP uses a staged funnel:

| stage | normal scale | decision role |
| --- | ---: | --- |
| screening | all eligible buses | triage and ranking |
| QSTS short | 3 buses | technical smoke validation only |
| QSTS stratified | 8-15 buses, normally 10-12 for the current benchmark | pre-demo comparison |
| QSTS full-year | 3-5 buses | investor reference |
| memo | 1-2 sites | commercial recommendation |

Short QSTS should cover a top candidate, a borderline candidate, and a constrained
control. Stratified QSTS should be balanced across top-ranked, borderline,
near-threshold no-go, and electrically diverse candidates. Full-year QSTS should be
reserved for final sites and calibration controls.

`thesegrid select-stratified-candidates` implements the screening-to-stratified
shortlist. Its default target is 12 buses: 5 top screening `go`, 3 borderline
`go-with-conditions`, 2 near-threshold `no-go`, and 2 constraint-diverse controls.

## Confidence

- `low`: QSTS short run. A clean result still needs annual validation.
- `medium`: QSTS stratified run. Useful for demo and ranking, but sampling can miss rare
  annual risk.
- `high`: QSTS full-year run. This is the strongest MVP evidence layer.

## Verdict Rules

`qsts_verdict` is retained as a legacy compatibility field. It uses configured absolute
P90 MW and MWh tolerances and remains useful for diagnostics and historical comparison.

The investor-facing decision should use the policy frontier when `decision_frontier.csv`
is available. The default selected policy is `standard`.

Policy verdicts are:

- `go`: no QSTS curtailment was observed.
- `go-with-conditions`: non-zero curtailment is within the selected policy limits.
- `investigate-only`: aggressive policy is satisfied but flexible policy is exceeded.
- `no-go`: at least one selected-policy limit is exceeded.

P90 MW alone is never sufficient for an investor decision. A case with P90 = 0 MW can
still be `no-go` if expected curtailed MWh exceeds tolerance.

QSTS now distinguishes sampled and decision-weighted energy:

- `sampled_curtailment_mwh`: raw curtailed MWh across evaluated timestamps.
- `weighted_curtailment_mwh`: MWh used for the QSTS decision. Full-year and short runs
  use 1 hour per evaluated timestamp; stratified annual samples weight each month/time
  block to represent the year.
- `curtailment_energy_ratio`: `weighted_curtailment_mwh / (requested_mw * 8760)`.

`evaluated_time_steps` means unique timestamps. `evaluated_bus_hours` means the
bus-time workload used for runtime and power-flow intensity metrics.

## Recommended Actions

| validation level | verdict | action |
| --- | --- | --- |
| `qsts_short` | `go` or `go-with-conditions` | `run_full_year_validation` |
| `qsts_short` | `no-go` | `resize_or_run_full_year_validation` |
| `qsts_stratified` | `go` or `go-with-conditions` | `run_full_year_validation` |
| `qsts_stratified` | `no-go` | `resize_or_run_full_year_validation` |
| `qsts_full_year` | `go` | `proceed_to_investor_memo` |
| `qsts_full_year` | `go-with-conditions` | `proceed_with_conditions` |
| `qsts_full_year` | `no-go` | `reject_or_resize_connection` |

## Validation Matrix

`thesegrid compare-validation` consolidates screening, QSTS short, QSTS stratified, and
one or more full-year QSTS CSV files into:

- `validation_matrix.csv`;
- `validation_matrix.md`.

The matrix should be read as the main calibration artifact for investor demos. It shows
where early evidence remains reliable and where it changes after full-year validation.

Key columns:

- `screening_verdict`: static triage verdict. It can be a false positive.
- `qsts_short_verdict`: smoke-test verdict. It is never investor-final.
- `qsts_stratified_verdict`: pre-demo verdict based on representative samples.
- `qsts_full_year_verdict`: legacy full-year QSTS verdict when available.
- `legacy_qsts_full_year_verdict`: explicit alias for the legacy verdict.
- `selected_policy`: policy used for the investor-facing final decision, default
  `standard`.
- `standard_policy_verdict` and `flexible_policy_verdict`: policy frontier verdicts
  used to show commercial risk appetite.
- `final_decision`: equals the selected-policy verdict when frontier rows are provided;
  otherwise falls back to the legacy full-year verdict or `requires_full_year_validation`.
- `calibration_status`: explains whether the early evidence was confirmed, changed, or
  still lacks full-year validation.

Calibration statuses:

| status | meaning |
| --- | --- |
| `confirmed_full_year` | Short or stratified evidence agrees with full-year evidence. |
| `false_positive_screening` | Static screening was acceptable, but full-year QSTS is `no-go`. |
| `false_positive_stratified` | Stratified QSTS was `go`, but full-year QSTS is `no-go`. |
| `changed_after_full_year` | A non-go stratified or short verdict changed after full-year QSTS. |
| `requires_full_year_validation` | No full-year run is available for this bus. |

## Resize Recommendation

`thesegrid qsts-resize` should be used when a requested MW is rejected but the site may
remain valuable at lower capacity. The resize output reports the original requested MW,
tested MW, delta MW from the original request, product decision, QSTS verdict, dominant
constraint, curtailment risk, and proxy delta NPV.

`qsts-resize` defaults to `selected_policy=standard`. The legacy QSTS verdict is
retained for compatibility, but `product_decision` and `acceptable` are based on the
selected decision-frontier policy.

Product decisions are:

| decision | meaning |
| --- | --- |
| `go` | Original requested MW is acceptable without observed QSTS curtailment. |
| `go-with-conditions` | Original requested MW is acceptable under the selected policy. |
| `resize-recommended` | Original requested MW is not acceptable, but a lower tested MW is acceptable under the selected policy. |
| `no-go` | Tested MW is not acceptable under the selected policy. |

`qsts_full_year` is the MVP reference layer, not an official grid-connection study.

## Current Campaign Interpretation

Use `experiments/simbench_standard_policy_campaign_v1.json` for the current
multi-network calibration campaign. The default investor-facing decision is the
`standard` policy frontier, not the legacy absolute `qsts_verdict`.

The product conclusion is: short and stratified QSTS are useful for triage and
comparison, but full-year QSTS is required before presenting an investor-grade
recommendation.
