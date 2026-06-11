# VoltPath Evidence Console

## Purpose

The evidence console is a local Streamlit interface for reading VoltPath result
artifacts. It is intentionally read-only: QSTS jobs still run through the CLI so long
simulations remain reproducible and restartable.

## Install

```bash
python -m pip install -e ".[ui]"
```

## Run

```bash
thesegrid-ui
```

Or:

```bash
python -m streamlit run src/thesegrid/ui.py
```

Then enter a result directory in the sidebar, for example:

```text
results/demo_pipeline_full_year
```

## Supported Artifacts

The console displays whichever files are present:

- `screening/screening.csv`
- `qsts_stratified/qsts_results.csv`
- `qsts_full_year/qsts_results.csv`
- `validation/validation_matrix.csv`
- `resize/resize_results.csv`
- `decision_frontier.csv`
- `qsts_risk_summary.csv`
- `contractual_envelope.csv`
- `static_vs_qsts_comparison.csv`
- `qsts_performance.json`
- `pipeline_manifest.json` or `run_manifest.json`

Missing files are allowed. The interface degrades to the available evidence level.

## Design Boundary

This UI is an evidence explorer for buyer-side pre-feasibility. It does not make
official grid-connection claims and does not replace RTE, Enedis, or consultant studies.
