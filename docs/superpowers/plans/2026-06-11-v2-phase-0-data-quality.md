# VoltPath V2 Phase 0 Data Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Portfolio Screening V2 traceable and safe enough for assisted pilot use by correcting ECO2MIX semantics, pinning ODRE identity input, versioning the score, enforcing Class A review, and emitting a per-run data-quality report.

**Architecture:** Keep source parsing in `public_data/`, identity loading in `substation_identity.py`, scoring in `portfolio_screening.py`, orchestration in `portfolio_workflow.py`, and client artifacts in `portfolio_reporting.py`. Source manifests carry immutable hashes and explicit provenance; scoring consumes normalized evidence but never infers connection capacity from regional storage presence.

**Tech Stack:** Python 3.10+, pandas, pytest, Ruff, existing VoltPath CLI and dataclasses.

---

### Task 1: Correct ECO2MIX semantics and missing values

**Files:**
- Modify: `src/thesegrid/public_data/eco2mix.py`
- Modify: `src/thesegrid/public_data/evidence.py`
- Test: `tests/test_public_data_eco2mix.py`
- Test: `tests/test_public_grid_evidence.py`

- [x] **Step 1: Add failing parser tests**

Add tests proving that `timestamp` is built from `Date` and `Heures`, `consumption_mw` comes from `Consommation`, missing quarter-hour measurements remain `NaN`, and the source interval is reported as 15 minutes.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest -q tests/test_public_data_eco2mix.py tests/test_public_grid_evidence.py
```

Expected: failures showing the existing shifted column mapping and zero-filled missing values.

- [x] **Step 3: Implement the corrected normalization**

Parse the source columns by their published names, retain nullable numeric values, add row-level measurement availability, and compute record count, interval, observed count, missing count, and covered hours without calling rows “hours”.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
pytest -q tests/test_public_data_eco2mix.py tests/test_public_grid_evidence.py
```

Expected: all focused tests pass.

### Task 2: Add source provenance and a pinned ODRE identity snapshot

**Files:**
- Modify: `src/thesegrid/public_data/sources.py`
- Modify: `src/thesegrid/public_data/odre.py`
- Modify: `src/thesegrid/substation_identity.py`
- Modify: `src/thesegrid/portfolio_workflow.py`
- Modify: `src/thesegrid/cli.py`
- Test: `tests/test_public_data_sources.py`
- Test: `tests/test_substation_identity.py`
- Test: `tests/test_portfolio_workflow.py`
- Test: `tests/test_assessment_and_cli.py`

- [x] **Step 1: Add failing provenance and local-snapshot tests**

Cover publisher, source URL, licence, publication or retrieval timestamp, transformation version, payload hash, and loading `ODRE/postes-electriques-rte.csv` without network access.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest -q tests/test_public_data_sources.py tests/test_substation_identity.py tests/test_portfolio_workflow.py tests/test_assessment_and_cli.py
```

Expected: failures for missing manifest fields and missing `--odre-substations` support.

- [x] **Step 3: Implement provenance and snapshot loading**

Extend manifests with explicit metadata, normalize both ODRE API and labelled snapshot schemas, hash the exact payload, add `PortfolioWorkflowRequest.odre_substations_path`, and expose `--odre-substations`.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the same focused command and expect all tests to pass.

### Task 3: Version the scoring policy and remove unsupported storage bonuses

**Files:**
- Modify: `src/thesegrid/portfolio_screening.py`
- Modify: `docs/portfolio-screening.md`
- Test: `tests/test_portfolio_screening.py`

- [x] **Step 1: Add failing policy tests**

Assert policy `portfolio-geospatial-v1` and prove that adding regional or source-substation battery capacity does not change the public-evidence score.

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
pytest -q tests/test_portfolio_screening.py
```

Expected: the old `v0` policy and storage bonuses cause failures.

- [x] **Step 3: Implement the documented V1 policy**

Score public evidence from source completeness only. Keep storage statistics as context and state explicitly that they are not evidence of connectability.

- [x] **Step 4: Run the focused test and verify GREEN**

Run the same focused command and expect all tests to pass.

### Task 4: Enforce Class A manual review

**Files:**
- Create: `src/thesegrid/portfolio_review.py`
- Modify: `src/thesegrid/portfolio_screening.py`
- Modify: `src/thesegrid/portfolio_workflow.py`
- Modify: `src/thesegrid/portfolio_reporting.py`
- Modify: `src/thesegrid/cli.py`
- Test: `tests/test_portfolio_review.py`
- Test: `tests/test_portfolio_screening.py`
- Test: `tests/test_portfolio_reporting.py`
- Test: `tests/test_portfolio_workflow.py`

- [x] **Step 1: Add failing review tests**

Cover validated review CSV input, pending Class A behavior, approved Class A behavior, rejected review behavior, and the generated `manual_review_queue.csv`.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest -q tests/test_portfolio_review.py tests/test_portfolio_screening.py tests/test_portfolio_reporting.py tests/test_portfolio_workflow.py
```

Expected: failures because no review contract or output exists.

- [x] **Step 3: Implement the review gate**

Add an optional `--manual-reviews` CSV. Class A is always review-required; without approval its Deep Dive recommendation remains conditional. Rejection prevents shortlisting. Reports expose status, reviewer, timestamp, notes, and pending actions.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the same focused command and expect all tests to pass.

### Task 5: Emit a per-run data-quality report

**Files:**
- Modify: `src/thesegrid/portfolio_reporting.py`
- Modify: `docs/portfolio-screening.md`
- Test: `tests/test_portfolio_reporting.py`

- [x] **Step 1: Add a failing bundle test**

Require `data_quality_report.json` with source traceability, source errors, ECO2MIX cadence and missingness, identity confidence counts, and Class A manual-review status.

- [x] **Step 2: Run the reporting test and verify RED**

Run:

```bash
pytest -q tests/test_portfolio_reporting.py
```

Expected: failure because the artifact is absent.

- [x] **Step 3: Implement the quality report**

Build the report only from manifests and screening results so it is deterministic for a fixed run. Include it in `PortfolioScreeningOutputs`, bundle summary, and `run_manifest.json`.

- [x] **Step 4: Run the reporting test and verify GREEN**

Run the same focused command and expect all tests to pass.

### Task 6: Verify the complete Phase 0 increment

**Files:**
- Modify: `docs/v2-market-analysis-and-roadmap.md`
- Modify: `docs/portfolio-screening.md`
- Regenerate: `results/portfolio-screening-v2-demo/`

- [x] **Step 1: Update assumptions and Phase 0 status**

Document corrected ECO2MIX semantics, nullable measurements, source metadata, V1 scoring, manual-review workflow, and remaining uncertainty.

- [x] **Step 2: Run the complete quality suite**

Run:

```bash
ruff check .
pytest -q
```

Expected: Ruff passes and all tests pass.

- [x] **Step 3: Run the reproducible Portfolio Screening demo**

Run:

```bash
PYTHONPATH=src python -m thesegrid.cli portfolio-screen \
  --portfolio examples/portfolio_sites.csv \
  --cartostock cartostock/postes_cartostock.csv \
  --output results/portfolio-screening-v2-demo \
  --rte7000-revision 1a2419a6f8a81ab212af035e811d4b893d7c4ccf \
  --rte7000-year 2023 \
  --rte7000-month 1 \
  --rte7000-snapshot 2023-01-01T00:00:00 \
  --search-radius-km 50 \
  --osm-fixture examples/osm_jalis_fixture.json \
  --odre-substations ODRE/postes-electriques-rte.csv \
  --odre-constraints ODRE/contraintes-region.csv \
  --odre-storage-assets ODRE/registre-national-installation-production-stockage-electricite-agrege.csv \
  --odre-regional-loads ODRE/soutirages-regionaux-quotidiens-provisoires-rpt.csv \
  --eco2mix-annual ECO2MIX/eCO2mix_RTE_Annuel-Definitif_2024.xls
```

Expected: the bundle uses policy V1, records the local ODRE hash, reports 15-minute ECO2MIX cadence and missing measurements, and queues all Class A sites for review.

- [x] **Step 4: Inspect generated evidence**

Confirm `run_manifest.json`, `data_quality_report.json`, `manual_review_queue.csv`, `portfolio_ranked.csv`, and `portfolio_screening_report.md` agree on policy and review status.
