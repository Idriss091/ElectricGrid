# RTE7000 Remote Data Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read one revision-pinned RTE7000 Parquet partition remotely from Hugging Face and return validated data with a reproducibility manifest.

**Architecture:** Add one focused module containing immutable request/result types, deterministic remote-path construction, injectable Parquet reading, schema validation, equality filtering, and provenance generation. Keep tests offline by injecting a fake reader.

**Tech Stack:** Python dataclasses, pandas, pyarrow/fsspec Hugging Face filesystem support, pytest, ruff.

---

### Task 1: Request and remote-path contract

**Files:**
- Create: `src/thesegrid/rte7000_data.py`
- Create: `tests/test_rte7000_data.py`

- [x] Write failing tests for valid remote path construction and invalid component,
  revision, year, month, columns, and filters.
- [x] Run `pytest tests/test_rte7000_data.py -q` and confirm import failure.
- [x] Implement immutable request and exception types plus deterministic `hf://` path
  construction.
- [x] Run `pytest tests/test_rte7000_data.py -q` and confirm the request tests pass.

### Task 2: Partition reading and provenance

**Files:**
- Modify: `src/thesegrid/rte7000_data.py`
- Modify: `tests/test_rte7000_data.py`

- [x] Write failing tests using an injected reader to assert the exact path, projected
  columns, equality filters, deterministic rows, and manifest fields.
- [x] Run the focused tests and confirm the reader behavior is missing.
- [x] Implement `read_rte7000_partition`, schema validation, filtering, exception
  wrapping, and UTC retrieval timestamps.
- [x] Run the focused tests and confirm they pass.

### Task 3: Package integration and verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/thesegrid/__init__.py`

- [x] Add `pyarrow` and `huggingface_hub` as runtime dependencies for remote Parquet
  access through the Hugging Face filesystem.
- [x] Export the request, result, manifest, exceptions, and reader function from the
  package public API.
- [x] Run `pytest tests/test_rte7000_data.py -q`.
- [x] Run `pytest -q` and record any pre-existing unrelated failure separately.
- [x] Run `ruff check src/thesegrid/rte7000_data.py tests/test_rte7000_data.py`.
- [x] Run `git diff --check`.
