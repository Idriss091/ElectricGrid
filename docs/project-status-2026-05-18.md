# Project Status - 2026-05-18

This is the current source of truth for the BESS pre-feasibility MVP. Older audit
documents and generated result folders remain useful as historical evidence, but this
file defines the current product state.

## Product Direction

Thesegrid is a buyer-side decision engine for flexible BESS grid-connection
pre-feasibility. It does not replace official network-operator studies.

The current investor decision output is:

- `go`;
- `go-with-conditions`;
- `no-go`.

## Current MVP Workflow

The current defensible workflow is:

1. Run static screening across candidate MV buses.
2. Run short QSTS as smoke validation.
3. Run stratified QSTS as pre-demo evidence.
4. Run full-year QSTS for investor-grade MVP validation.
5. Generate a validation matrix comparing early verdicts against full-year evidence.
6. Use the QSTS memo and contractual envelope as the investor-facing bundle.

Screening, short QSTS, and stratified QSTS are not final investor verdicts. Full-year
QSTS is the strongest MVP validation layer, but it is still not an official
grid-connection study.

## Canonical Commands

```bash
thesegrid screen --network 1-MV-rural--0-sw --requested-mw 5 --output <output_dir>
thesegrid qsts --network 1-MV-rural--0-sw --screening-csv <screening.csv> --requested-mw 5 --bus-ids 2,21,24 --output <output_dir>
thesegrid qsts-sweep --config <sweep.json> --output <output_dir>
thesegrid compare-validation --screening-csv <screening.csv> --qsts-short <qsts_results.csv> --qsts-stratified <qsts_results.csv> --qsts-full-year <qsts_results.csv> --output <output_dir>
```

## Current Source Of Truth

Use these documents for current product interpretation:

- `docs/project-status-2026-05-18.md`;
- `docs/france-bess-connection-context.md`;
- `docs/decision-policy.md`;
- `docs/demo-script.md`;
- `docs/interpretation-guide.md`;
- `docs/data-and-modeling.md`;
- `docs/product-spec.md`;
- `docs/research-protocol.md`.

Use these generated bundles as current reproducible evidence:

- `results/demo_investor_2026-05-18/`;
- `results/decision_policy_2026-05-18/`;
- `results/full_year_calibration_2026-05-18/`.

## Historical Material

These documents are historical logs, not current source of truth:

- `docs/benchmark-log.md`;
- `docs/current-state-and-qsts-next-steps.md`.

Only these historical result directories remain under
`results/archive/legacy_2026-05-18/`:

- `qsts_envelope_2026-05-09/`: first QSTS envelope bundle;
- `qsts_memo_manifest_2026-05-13/`: manifest and memo generation milestone;
- `qsts_performance_2026-05-13/`: earlier performance and sweep benchmark;
- `qsts_risk_summary_2026-05-13/`: tail-risk summary milestone;
- `state_check_2026-05-18/`: pre-policy state check;
- `state_check_2026-05-18_policy/`: policy-transition state check.

Older `audit_*`, `corrected_*`, `final_*`, `*_smoke*`, and `validation_sweep/` result
directories were deleted because they were redundant with tests or superseded by the
current canonical bundles.

## Current Decision Policy

Verdicts must be interpreted with a validation level:

- `screening_only`: triage only;
- `qsts_short`: smoke validation only;
- `qsts_stratified`: pre-demo evidence;
- `qsts_full_year`: MVP investor reference.

P90 curtailed MW alone is not sufficient for an investor decision. Expected curtailed
MWh can reject a bus even when P90 MW is zero or below tolerance.

## Current Calibration Evidence

The full-year calibration matrix currently shows:

| bus | screening | short | stratified | full-year | final decision | status |
| ---: | --- | --- | --- | --- | --- | --- |
| 2 | `go` | `go` | `go` | `no-go` | `no-go` | `false_positive_stratified` |
| 21 | `no-go` | `go-with-conditions` | `no-go` | `no-go` | `no-go` | `changed_after_full_year` |
| 24 | `no-go` | `go-with-conditions` | `no-go` | not run | `requires_full_year_validation` | `requires_full_year_validation` |

## Cleanup Policy

Keep production logic in `src/thesegrid/` and tests in `tests/`.

Generated artifacts should stay under `results/` and remain ignored by git. If a result
bundle is important, document it here or in a specific run note rather than committing
large generated CSVs.

Local generated folders such as `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`,
`.venv/`, and `*.egg-info/` are not part of the project state.

Scientific PDFs are currently tracked as source material. If the collection grows, move
them to external storage or Git LFS and keep `docs/sources.md` as the index.

## Current Gaps

- Full-year QSTS runtime is too high for synchronous SaaS use.
- QSTS compute needs job orchestration before a SaaS interface.
- The economic layer remains a proxy and should not be presented as bankable revenue
  modelling.
- The contractual envelope is RTE/CRE-inspired, not an official offer.
- More calibrated full-year cases are needed before broad claims about stratified
  sampling reliability.

## Current Implementation Priorities

- Keep V1 focused on BESS France and avoid broad large-load expansion before the BESS
  decision bundle is credible.
- Use explicit `rte_cre_inspired_v1` gabarit rule objects for direction, season,
  time-block, source label, validity date, and prudence level.
- Use `experiments/investor_mvp_calibration.json` for the next calibration campaign.
- Treat `parallelization_unit = bus` as the future QSTS worker boundary.
- Keep all revenue and NPV fields labelled as proxy economics, not bankable modelling.
