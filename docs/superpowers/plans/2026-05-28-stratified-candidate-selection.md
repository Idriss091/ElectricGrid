# Stratified Candidate Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an automatic screening-to-stratified-QSTS shortlist selector.

**Architecture:** Add a small pure-Python selector that reads `screening.csv`, chooses a balanced set of bus IDs, and writes a CSV that can feed `thesegrid qsts --bus-ids`. Expose it through the existing argparse CLI and document the command in the current workflow docs.

**Tech Stack:** Python dataclasses, csv module, pytest, ruff.

---

### Task 1: Selection Function And CSV Output

**Files:**
- Create: `src/thesegrid/stratified_selection.py`
- Test: `tests/test_stratified_selection.py`

- [ ] Write tests for default balanced selection from screening rows.
- [ ] Implement `StratifiedSelectionRequest`, `StratifiedCandidate`, `select_stratified_candidates`, and `write_stratified_selection_csv`.
- [ ] Verify `python -m pytest tests/test_stratified_selection.py -q`.

### Task 2: CLI Command

**Files:**
- Modify: `src/thesegrid/cli.py`
- Test: `tests/test_stratified_selection.py`

- [ ] Add `thesegrid select-stratified-candidates --screening-csv <path> --output <path>`.
- [ ] Add a CLI test proving the command writes selected bus rows.
- [ ] Verify `python -m pytest tests/test_stratified_selection.py -q`.

### Task 3: Documentation And Full Verification

**Files:**
- Modify: `docs/project-status-2026-05-18.md`
- Modify: `docs/research-protocol.md`

- [ ] Add the canonical command and explain how to pass selected bus IDs to QSTS.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check .`.
