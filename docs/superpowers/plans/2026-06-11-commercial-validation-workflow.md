# Commercial Validation Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn roadmap Phases 1-3 into a reproducible workflow that evaluates customer interviews, paid Portfolio Screening pilots, and screening calibration against deeper evidence.

**Architecture:** A typed `commercial_validation` module parses three pseudonymized CSV contracts and computes roadmap gates without changing score thresholds. A separate reporting module writes deterministic JSON, CSV, and Markdown outputs; the CLI exposes one `pilot-evaluate` command so external evidence can be added incrementally.

**Tech Stack:** Python 3.10+, dataclasses, csv, pathlib, datetime, json, pytest, Ruff.

---

### Task 1: Interview discovery contract and gates

**Files:**
- Create: `src/thesegrid/commercial_validation.py`
- Create: `tests/test_commercial_validation.py`

- [x] **Step 1: Write failing interview parsing tests**

Cover required columns, unique `interview_id`, accepted segments, strict boolean values,
non-negative optional numbers, and completed-interview filtering.

- [x] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/test_commercial_validation.py
```

Expected: import failure because the module does not exist.

- [x] **Step 3: Implement interview records**

Define `InterviewRecord`, `CommercialValidationError`, and
`load_interview_records(path)`. The contract uses pseudonymous `organization_id` and
excludes names, email addresses, and phone numbers.

- [x] **Step 4: Implement interview metrics**

Define `evaluate_interviews(records)` with:

- completed interview count;
- segment counts;
- grid-risk top-three percentage;
- late-grid-information loss percentage;
- shared-portfolio count;
- pilot-interest count;
- paid-pilot-interest count;
- budget, internal-tool sufficiency, private-data dependency, and comparison-consent
  counts;
- decision `go`, `reposition`, `no-go`, or `insufficient_evidence`.

The `go` decision requires all six roadmap thresholds. Insufficient completed interviews
must never produce `go`.

- [x] **Step 5: Verify GREEN**

Run the focused test and expect all interview tests to pass.

### Task 2: Pilot performance and unit economics

**Files:**
- Modify: `src/thesegrid/commercial_validation.py`
- Modify: `tests/test_commercial_validation.py`

- [x] **Step 1: Write failing pilot tests**

Cover 20-100 site portfolios, signed agreement and frozen-source flags, delivery working
days, billed revenue, labor cost, other cost, identity corrections, recommendation
comprehension, changed priorities, Deep Dive conversion, reuse request, and 30-day
decision follow-up.

- [x] **Step 2: Verify RED**

Run the focused test and confirm failures for missing pilot APIs.

- [x] **Step 3: Implement pilot records and evaluation**

Define `PilotRecord`, `load_pilot_records(path)`, and `evaluate_pilots(records)`. Gross
margin is:

```text
billed_eur - human_hours * labor_cost_eur_per_hour - other_cost_eur
```

Report aggregate and per-pilot rates. Do not infer payment from pilot interest; paid
pilots require positive `billed_eur`.

- [x] **Step 4: Verify GREEN**

Run the focused test and expect all pilot tests to pass.

### Task 3: Ground-truth registry and calibration metrics

**Files:**
- Modify: `src/thesegrid/commercial_validation.py`
- Modify: `tests/test_commercial_validation.py`

- [x] **Step 1: Write failing ground-truth tests**

Cover unique record/site keys, A-D screening classes, professional-review status,
evidence types, evidence outcomes, actual decisions, region, voltage, and outcome dates.

- [x] **Step 2: Verify RED**

Run the focused test and confirm failures for missing calibration APIs.

- [x] **Step 3: Implement calibration evaluation**

Define `GroundTruthRecord`, `load_ground_truth_records(path)`, and
`evaluate_ground_truth(records)`.

Prediction-positive classes are A/B. Deep-evidence-positive outcomes are
`viable` and `conditional`; `not_viable` is negative; `inconclusive` is excluded from
false-positive and false-negative denominators.

Compute:

- professionally reviewed sites;
- sites with consultant, exploratory-study, PTF, or operator evidence;
- represented regions and voltage levels;
- true positives, true negatives, false positives, and false negatives;
- precision, recall, false-positive rate, and false-negative rate where denominators
  exist;
- readiness against 50 reviewed sites, 15 deep-evidence sites, two regions, and two
  voltage levels.

No threshold recalibration occurs in this increment.

- [x] **Step 4: Verify GREEN**

Run the focused test and expect all calibration tests to pass.

### Task 4: Consolidated outputs and CLI

**Files:**
- Create: `src/thesegrid/commercial_reporting.py`
- Modify: `src/thesegrid/cli.py`
- Modify: `src/thesegrid/__init__.py`
- Create: `tests/test_commercial_reporting.py`
- Modify: `tests/test_assessment_and_cli.py`

- [x] **Step 1: Write failing report and CLI tests**

Require:

- `commercial_validation_summary.json`;
- `commercial_validation_report.md`;
- `interview_metrics.csv`;
- `pilot_metrics.csv`;
- `calibration_metrics.csv`;
- a source manifest containing hashes of all three input files;
- `thesegrid pilot-evaluate --interviews ... --pilots ... --ground-truth ... --output ...`.

- [x] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/test_commercial_reporting.py tests/test_assessment_and_cli.py
```

Expected: failures for missing reporter and command.

- [x] **Step 3: Implement reporting**

The report must distinguish:

- measured evidence;
- roadmap threshold;
- pass/fail/not-measured status;
- remaining external actions.

Empty header-only inputs produce `insufficient_evidence`, not errors or false success.

- [x] **Step 4: Implement CLI**

Add `pilot-evaluate` arguments and return exit code 0 for a valid evaluation regardless
of commercial decision. Invalid contracts return exit code 2 with a clear message.

- [x] **Step 5: Verify GREEN**

Run the focused tests and expect all report and CLI tests to pass.

### Task 5: Templates, guide, and roadmap integration

**Files:**
- Create: `examples/commercial_validation/interviews.csv`
- Create: `examples/commercial_validation/pilots.csv`
- Create: `examples/commercial_validation/ground_truth.csv`
- Create: `docs/commercial-validation.md`
- Modify: `docs/v2-market-analysis-and-roadmap.md`

- [x] **Step 1: Add header-only pseudonymized templates**

Templates contain no fabricated interviews, clients, payments, or study outcomes.

- [x] **Step 2: Document the workflow**

Document every field, accepted enum, formula, threshold, privacy boundary, and command.
State explicitly that software readiness does not satisfy the external interview and
pilot gates.

- [x] **Step 3: Update roadmap status**

Mark only the tooling and register preparation as implemented. Leave interview counts,
pilot counts, payment, customer outcomes, and calibration thresholds unchecked until
real evidence exists.

### Task 6: End-to-end verification

**Files:**
- Generate: `results/commercial-validation-empty/`

- [ ] **Step 1: Run the complete suite**

```bash
ruff check .
pytest -q
```

- [ ] **Step 2: Run the empty-evidence workflow**

```bash
PYTHONPATH=src python -m thesegrid.cli pilot-evaluate \
  --interviews examples/commercial_validation/interviews.csv \
  --pilots examples/commercial_validation/pilots.csv \
  --ground-truth examples/commercial_validation/ground_truth.csv \
  --output results/commercial-validation-empty
```

Expected: valid outputs with `insufficient_evidence`, zero measured external outcomes,
and no fabricated commercial success.

- [ ] **Step 3: Inspect outputs**

Confirm input hashes, roadmap thresholds, empty denominators, and remaining external
actions agree across JSON, CSV, and Markdown.
