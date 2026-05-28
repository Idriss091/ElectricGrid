# Thesegrid Pipeline Demo

This runbook defines the current single-command BESS evidence demo.

## Goal

Produce one reproducible buyer-side pre-feasibility bundle from static screening through
full-year QSTS, validation matrix, and investor report.

This remains a SimBench workflow demonstration. It does not prove feasibility for a real
French site and does not replace an official connection study.

## Recommended Command

Install the local CLI first when needed:

```bash
python -m pip install -e .
```

Use this quick smoke command while iterating:

```bash
thesegrid run-pipeline \
  --network 1-MV-rural--0-sw \
  --requested-mw 5 \
  --max-buses 3 \
  --stratified-max-candidates 1 \
  --stratified-top-go-candidates 1 \
  --stratified-borderline-candidates 0 \
  --stratified-near-threshold-no-go-candidates 0 \
  --stratified-constraint-diverse-candidates 0 \
  --qsts-p90-curtailment-tolerance-mw 3 \
  --qsts-expected-curtailment-tolerance-mwh 60 \
  --qsts-progress-every-n-hours 0 \
  --run-qsts-stratified \
  --output results/demo_pipeline_stratified_smoke
```

Use this full evidence command as a longer job:

```bash
thesegrid run-pipeline \
  --network 1-MV-rural--0-sw \
  --requested-mw 5 \
  --max-buses 20 \
  --stratified-max-candidates 5 \
  --full-year-max-candidates 1 \
  --full-year-top-candidates 1 \
  --full-year-borderline-candidates 0 \
  --full-year-bad-controls 0 \
  --qsts-p90-curtailment-tolerance-mw 3 \
  --qsts-expected-curtailment-tolerance-mwh 60 \
  --run-qsts-stratified \
  --run-qsts-full-year \
  --output results/demo_pipeline_full_year
```

Use a lower `--max-buses` or keep `--full-year-max-candidates 1` while iterating locally.
Increase the finalist count only when runtime is acceptable. Full-year QSTS can take
several minutes per finalist on a laptop and should be treated as a job, not a quick
unit-test-style check.

## Required Outputs

The demo is valid when these files exist:

- `pipeline_report.md`
- `pipeline_manifest.json`
- `screening/screening.csv`
- `stratified_candidate_selection.csv`
- `qsts_stratified/qsts_results.csv`
- `full_year_candidate_selection.csv`
- `qsts_full_year/qsts_results.csv`
- `validation/validation_matrix.csv`
- `validation_matrix.csv`
- `investor_report.html`
- `scorecard.md`
- `next_calibration_campaign.md`

## Reading Order

1. Open `pipeline_report.md` for the workflow status and evidence boundary.
2. Open `scorecard.md` for the compact evidence state.
3. Open `investor_report.html` for the client-facing bundle.
4. Inspect `validation/validation_matrix.csv` when a verdict changes between screening,
   stratified QSTS, and full-year QSTS.
5. Inspect `pipeline_manifest.json` before sharing results, because it records the
   network, requested MW, BESS-lite assumptions, and evidence level.

## Acceptance Criteria

- The report labels `data_source_type` as `benchmark` unless a client model is used.
- Full-year evidence is present before investor-facing flexible-envelope claims.
- The bundle states that it is a buyer-side pre-feasibility aid, not an official
  RTE/Enedis study, PTF, or offer.
- Any `go` or `go-with-conditions` claim is tied to the reported evidence level and
  configured curtailment tolerances.
