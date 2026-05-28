# Project Status - 2026-05-18

This is a historical status note. The current implementation source of truth is now:

- `docs/product-spec.md` for product scope;
- `docs/demo-pipeline.md` for the runnable pipeline demo;
- `docs/data-and-modeling.md` and `docs/assumptions.md` for modelling assumptions.

Older audit documents and generated result folders remain useful as historical
evidence, but generated `results/` folders are local artifacts and are not required in
git.

## Product Direction

Thesegrid is a buyer-side decision engine for flexible BESS grid-connection
pre-feasibility. It does not replace official network-operator studies.

The current investor decision output is:

- `go`;
- `go-with-conditions`;
- `no-go`.

## Current MVP Workflow

The defensible workflow is a staged evidence funnel, not "run every study on every bus":

1. Run static screening across all eligible candidate MV buses.
2. Run short QSTS as smoke validation on a small representative set.
3. Run stratified QSTS as pre-demo evidence on a balanced shortlist.
4. Run full-year QSTS only for final candidate sites and calibration controls.
5. Generate a validation matrix comparing early verdicts against full-year evidence.
6. Use the QSTS memo and contractual envelope as the investor-facing bundle.

Screening, short QSTS, and stratified QSTS are not final investor verdicts. Full-year
QSTS is the strongest MVP validation layer, but it is still not an official
grid-connection study.

For the current `1-MV-rural--0-sw` benchmark, which has roughly 100 eligible MV
candidates, the target campaign size is:

| stage | target size | role |
| --- | ---: | --- |
| static screening | all eligible buses | low-cost triage and constraint discovery |
| short QSTS | 3 buses | smoke-test one top bus, one borderline bus, and one constrained control |
| stratified QSTS | 10-12 buses | pre-demo comparison across top, borderline, near-threshold no-go, and electrically diverse buses |
| full-year QSTS | 3-5 buses | investor reference for final candidates and selected calibration controls |
| investor memo | 1-2 sites | commercial recommendation after full-year evidence or explicit validation caveat |

For other networks, keep the same proportions: screen all eligible buses, run short QSTS
on 3 buses, run stratified QSTS on `min(15, max(8, about 10-15% of useful candidate
buses))`, and reserve full-year QSTS for 3-5 final or calibration cases.

## Canonical Commands

Use `run-pipeline` for the current integrated workflow:

```bash
thesegrid run-pipeline \
  --network 1-MV-rural--0-sw \
  --requested-mw 5 \
  --run-qsts-stratified \
  --output results/demo_pipeline_stratified_smoke
```

Use the lower-level commands only for debugging or research campaigns:

```bash
thesegrid screen --network <network_code> --requested-mw <mw> --output <output_dir>
thesegrid select-stratified-candidates --screening-csv <screening.csv> --output <stratified_candidates.csv>
thesegrid qsts --network <network_code> --screening-csv <screening.csv> --requested-mw <mw> --bus-ids-csv <stratified_candidates.csv> --stratified-sample --output <output_dir>
thesegrid select-full-year-candidates --screening-csv <screening.csv> --stratified-csv <qsts_results.csv> --output <full_year_candidates.csv>
thesegrid compare-validation --screening-csv <screening.csv> --qsts-stratified <qsts_results.csv> --qsts-full-year <qsts_results.csv> --output <output_dir>
thesegrid render-bundle --bundle <bundle_dir>
```

## Current Source Of Truth

Use these documents for current product interpretation:

- `docs/product-spec.md`;
- `docs/demo-pipeline.md`;
- `docs/assumptions.md`;
- `docs/france-bess-connection-context.md`;
- `docs/decision-policy.md`;
- `docs/interpretation-guide.md`;
- `docs/data-and-modeling.md`;
- `docs/research-protocol.md`.

Generated bundles under `results/` are local, reproducible artifacts. They should be
regenerated with `docs/demo-pipeline.md` rather than treated as checked-in source.

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

## QSTS Semantics Correction

QSTS performance and risk outputs distinguish unique timestamps from bus-hours:
`evaluated_time_steps` is the timestamp count, while `evaluated_bus_hours` is the
runtime workload. QSTS also separates raw sampled MWh from weighted MWh; stratified
annual samples use weighted MWh for decision checks and keep sampled MWh for diagnostic
traceability.

## Current Implementation Priorities

- Keep V1 focused on BESS France and avoid broad large-load expansion before the BESS
  decision bundle is credible.
- Use explicit `rte_cre_inspired_v1` gabarit rule objects for direction, season,
  time-block, source label, validity date, and prudence level.
- Use `experiments/investor_mvp_calibration.json` for the next calibration campaign.
- Treat `parallelization_unit = bus` as the future QSTS worker boundary.
- Keep all revenue and NPV fields labelled as proxy economics, not bankable modelling.
