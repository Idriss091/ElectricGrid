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

## Confidence

- `low`: QSTS short run. A clean result still needs annual validation.
- `medium`: QSTS stratified run. Useful for demo and ranking, but sampling can miss rare
  annual risk.
- `high`: QSTS full-year run. This is the strongest MVP evidence layer.

## Verdict Rules

- `go`: no QSTS curtailment was observed.
- `go-with-conditions`: QSTS curtailment is non-zero but both P90 MW and expected MWh are
  within configured tolerances.
- `no-go`: P90 MW, expected MWh, or both exceed configured tolerances.

P90 MW alone is never sufficient for an investor decision. A case with P90 = 0 MW can
still be `no-go` if expected curtailed MWh exceeds tolerance.

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
- `qsts_full_year_verdict`: strongest MVP verdict when available.
- `final_decision`: equals the full-year verdict when a full-year run exists; otherwise
  `requires_full_year_validation`.
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

Product decisions are:

| decision | meaning |
| --- | --- |
| `go` | Original requested MW is acceptable without observed QSTS curtailment. |
| `go-with-conditions` | Original requested MW is acceptable within configured tolerances. |
| `resize-recommended` | Original requested MW is not acceptable, but a lower tested MW is acceptable. |
| `no-go` | Tested MW is not acceptable under configured tolerances. |

`qsts_full_year` is the MVP reference layer, not an official grid-connection study.

## Current Demo Interpretation

The canonical demo under `results/demo_investor_2026-05-18/` shows why this policy is
needed:

- bus 2 is `go` in the stratified run;
- bus 2 becomes `no-go` in the full-year run because expected curtailed energy reaches
  120.977 MWh while P90 remains 0 MW;
- buses 21 and 24 exceed the 60 MWh tolerance in the stratified run despite P90 remaining
  below the 3 MW tolerance.

The product conclusion is: short and stratified QSTS are useful for triage and demo, but
full-year QSTS is required before presenting an investor-grade recommendation.
