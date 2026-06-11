# Portfolio Screening Geospatial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reproducible command that ranks a client BESS portfolio using nearby French transmission substations and traceable public evidence.

**Architecture:** Separate portfolio validation, OSM access, deterministic screening,
and report writing into focused modules. Keep network access injectable and the scoring
policy versioned so unit tests are offline and pilot calibration can evolve without
rewriting source adapters.

**Tech Stack:** Typed Python, dataclasses, pandas, urllib, pytest, ruff, OpenStreetMap
Overpass, Cartostock, ODRE, remotely projected RTE7000 Parquet.

---

### Task 1: Portfolio input contract

**Files:**
- Create: `src/thesegrid/portfolio_input.py`
- Create: `tests/test_portfolio_input.py`

- [ ] Write failing tests for valid rows, duplicate IDs, coordinate ranges, positive
  project values, optional fields, and row-level error messages.
- [ ] Run `pytest tests/test_portfolio_input.py -v` and confirm import failure.
- [ ] Implement immutable site records, validation errors, and CSV loading.
- [ ] Run `pytest tests/test_portfolio_input.py -v` and confirm all tests pass.

### Task 2: Bounded OSM substation access

**Files:**
- Create: `src/thesegrid/osm_substations.py`
- Create: `tests/test_osm_substations.py`

- [ ] Write failing tests for Overpass query bounds, RTE/voltage filtering, coordinate
  extraction, voltage parsing, haversine distance, provenance, and source failures.
- [ ] Run `pytest tests/test_osm_substations.py -v` and confirm import failure.
- [ ] Implement the injectable Overpass adapter and normalized candidate records.
- [ ] Run `pytest tests/test_osm_substations.py -v` and confirm all tests pass.

### Task 3: Conservative OSM-to-canonical linking

**Files:**
- Modify: `src/thesegrid/substation_identity.py`
- Modify: `tests/test_substation_identity.py`

- [ ] Write failing tests for ODRE-code, normalized-name-and-voltage, unique-name,
  ambiguous, and unmatched OSM links.
- [ ] Run the focused identity tests and confirm the new API is missing.
- [ ] Implement deterministic geographic-source links without fuzzy matching.
- [ ] Run the identity tests and confirm all tests pass.

### Task 4: Explainable screening policy

**Files:**
- Create: `src/thesegrid/portfolio_screening.py`
- Create: `tests/test_portfolio_screening.py`

- [ ] Write failing tests for score dimensions, evidence gates, classes, recommended
  actions, missing evidence, maximum-distance handling, and deterministic ranking.
- [ ] Run `pytest tests/test_portfolio_screening.py -v` and confirm import failure.
- [ ] Implement policy `portfolio-geospatial-v0`, candidate selection, and ranking.
- [ ] Run `pytest tests/test_portfolio_screening.py -v` and confirm all tests pass.

### Task 5: Client deliverables

**Files:**
- Create: `src/thesegrid/portfolio_reporting.py`
- Create: `tests/test_portfolio_reporting.py`

- [ ] Write failing tests for ranked CSV, candidate CSV, executive Markdown, standalone
  HTML map, assumption register, and reproducible manifest.
- [ ] Run `pytest tests/test_portfolio_reporting.py -v` and confirm import failure.
- [ ] Implement deterministic writers and required commercial warnings.
- [ ] Run `pytest tests/test_portfolio_reporting.py -v` and confirm all tests pass.

### Task 6: CLI and public API

**Files:**
- Modify: `src/thesegrid/cli.py`
- Modify: `src/thesegrid/__init__.py`
- Modify: `tests/test_assessment_and_cli.py`
- Create: `docs/portfolio-screening.md`
- Create: `examples/portfolio_sites.csv`

- [ ] Write a failing CLI integration test for `portfolio-screen`.
- [ ] Run the focused CLI test and confirm the command is unknown.
- [ ] Add CLI arguments for portfolio, output, Cartostock path, RTE7000 revision and
  snapshot, search radius, and optional offline OSM fixture.
- [ ] Export the stable APIs and document the exact client workflow and limitations.
- [ ] Run the focused CLI tests and confirm they pass.

### Task 7: End-to-end verification

**Files:**
- Modify only files required by failures attributable to this tranche.

- [ ] Run all new focused tests.
- [ ] Run `ruff check` on changed Python files.
- [ ] Run `pytest -q` and separate pre-existing failures from regressions.
- [ ] Run a live bounded OSM query and a projected remote RTE7000 snapshot query.
- [ ] Run `portfolio-screen` on the example portfolio and inspect every deliverable.
- [ ] Run `git diff --check`.
