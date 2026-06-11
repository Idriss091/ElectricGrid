# French Substation Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce conservative, traceable Cartostock-to-ODRE-to-RTE7000 substation identities without fuzzy matching.

**Architecture:** Use one module for source dataclasses, normalization, source loading, deterministic matching, and RTE7000 enrichment. Readers and fetchers are injectable so the unit suite remains offline.

**Tech Stack:** Python dataclasses, pandas, urllib, pytest, ruff.

---

### Task 1: Cartostock normalization

**Files:**
- Create: `src/thesegrid/substation_identity.py`
- Create: `tests/test_substation_identity.py`

- [x] Write failing tests for French name normalization, address parsing, voltage
  extraction, expected schema, and deterministic Cartostock records.
- [x] Run the focused tests and confirm the module is missing.
- [x] Implement the Cartostock types and loader.
- [x] Run the focused tests and confirm Task 1 is green.

### Task 2: ODRE loading and provenance

**Files:**
- Modify: `src/thesegrid/substation_identity.py`
- Modify: `tests/test_substation_identity.py`

- [x] Write failing tests for CSV fetch injection, schema validation, normalized ODRE
  records, and JSON-safe provenance.
- [x] Run the focused tests and confirm the behavior is missing.
- [x] Implement the ODRE loader, manifest, and dedicated source errors.
- [x] Run the focused tests and confirm Task 2 is green.

### Task 3: Conservative matching and RTE7000 enrichment

**Files:**
- Modify: `src/thesegrid/substation_identity.py`
- Modify: `tests/test_substation_identity.py`
- Modify: `src/thesegrid/__init__.py`

- [x] Write failing tests for exact, high, ambiguous, unmatched, and exact RTE7000-code
  enrichment behavior.
- [x] Run the focused tests and confirm matching behavior is missing.
- [x] Implement deterministic matching and public exports.
- [x] Run focused tests, package lint, full pytest, and `git diff --check`.
