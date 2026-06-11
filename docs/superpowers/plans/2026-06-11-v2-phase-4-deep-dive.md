# V2 Phase 4 Deep Dive Implementation Plan

> **For agentic workers:** Use `superpowers:test-driven-development` for every
> behavioral increment and `superpowers:systematic-debugging` for native-engine
> failures.

**Goal:** Produce a reproducible buyer-side Deep Dive that loads one pinned D-GITT
XIIDM snapshot, validates a manually selected connection node, records the structural
model, applies explicit operating-state assumptions, and tests BESS injection and
withdrawal scenarios without presenting an official connection capacity.

**Architecture:** Keep data acquisition, operating-state reconstruction, network-engine
execution, and reporting separate. The core workflow depends on a small engine protocol
so contract and decision tests run without the native PyPowSyBl library. The production
adapter imports PyPowSyBl lazily and records its version, provider, parameters, network
revision, snapshot hash, node identity, and every changed injection.

**Scientific boundary:** D-GITT snapshots are valid at the equipment level and contain
missing steady-state hypotheses (`target_p`, `p0`, and related fields can be `NaN`).
Loading topology is not equivalent to reconstructing an operating state. A load-flow
or capacity result is prohibited until all required steady-state assumptions are
explicit, validated, and included in the run manifest.

---

### Task 1: Targeted D-GITT snapshot access

**Files:**
- Create: `src/thesegrid/dgitt_data.py`
- Create: `tests/test_dgitt_data.py`

- [x] Define a request with repository, immutable revision, timestamp, and bounded cache.
- [x] Derive the canonical five-minute XIIDM path for years 2021-2023.
- [x] Reject non-five-minute timestamps and mutable revisions.
- [x] Download exactly one file through an injected Hugging Face downloader.
- [x] Record repository, revision, remote path, timestamp, size, SHA-256, license,
  retrieval time, and local cache path.
- [x] Wrap missing, corrupted, and remote-access failures with actionable errors.

### Task 2: Deep Dive input contract

**Files:**
- Create: `src/thesegrid/deep_dive.py`
- Create: `tests/test_deep_dive.py`

- [ ] Parse a Portfolio Screening handoff package.
- [ ] Require an approved manual review for Class A.
- [ ] Require explicit XIIDM voltage-level and bus/breaker bus identifiers.
- [ ] Validate requested MW, scenario increments, injection/withdrawal directions,
  voltage assumptions, and policy/source versions.
- [ ] Reject any handoff that claims geospatial identity alone proves electrical
  connectivity.

### Task 3: Structural inventory and state-readiness gate

**Files:**
- Modify: `src/thesegrid/deep_dive.py`
- Modify: `tests/test_deep_dive.py`

- [ ] Define a network-engine protocol and deterministic fake.
- [ ] Inventory substations, voltage levels, buses, lines, transformers, generators,
  loads, connected components, and operational limits.
- [ ] Verify the manually selected bus exists in the selected voltage level.
- [ ] Measure missing generator and load steady-state hypotheses.
- [ ] Return `operating_state_missing` without executing scenarios when required values
  remain absent.

### Task 4: Explicit operating-state reconstruction

**Files:**
- Create: `src/thesegrid/operating_state.py`
- Create: `tests/test_operating_state.py`

- [ ] Define a versioned CSV contract for generator targets, load P/Q, boundary
  injections, disabled equipment, source method, and uncertainty.
- [ ] Apply assumptions only to known equipment IDs.
- [ ] Reject partial or non-finite values required for steady-state validation.
- [ ] Record coverage, totals, unresolved equipment, source category, and hashes.
- [ ] Do not infer nodal injections from regional totals without a documented allocation
  policy.

### Task 5: PyPowSyBl execution adapter

**Files:**
- Create: `src/thesegrid/pypowsybl_engine.py`
- Create: `tests/test_pypowsybl_engine.py`
- Modify: `pyproject.toml`

- [ ] Add a `deep-dive` optional dependency containing `pypowsybl`.
- [ ] Import PyPowSyBl lazily and report installation/runtime failures.
- [ ] Load XIIDM with the minimum validation level needed for reconstruction.
- [ ] Apply the versioned operating state and validate steady-state hypotheses.
- [ ] Run the baseline AC load flow with explicit provider and parameters.
- [ ] Use variants for each BESS injection and withdrawal step.
- [ ] Create separate generator and load representations at the validated bus.
- [ ] Extract convergence, voltage, branch current/power, operational-limit loading,
  slack mismatch, and binding constraints.
- [ ] Keep DC and N-1 analyses disabled until their assumptions and interpretation are
  separately validated.

### Task 6: Reports and CLI

**Files:**
- Create: `src/thesegrid/deep_dive_reporting.py`
- Modify: `src/thesegrid/cli.py`
- Modify: `src/thesegrid/__init__.py`
- Create: `tests/test_deep_dive_reporting.py`
- Modify: `tests/test_assessment_and_cli.py`

- [ ] Add `thesegrid deep-dive`.
- [ ] Write structural inventory, scenario results, constraints, assumptions, source
  manifest, and an executive Markdown report.
- [ ] Separate official facts, public reconstruction, supplied assumptions, calculated
  results, and unavailable evidence.
- [ ] Refuse a `go` verdict when the baseline does not converge or the operating state is
  incomplete.
- [ ] Use buyer-side `go-with-conditions`, `no-go`, or `insufficient-evidence` language
  only after the relevant evidence gates.

### Task 7: Real-engine verification

**Files:**
- Generate ignored outputs under: `results/deep-dive/`

- [ ] Verify the isolated project virtualenv can import PyPowSyBl and record its version.
- [ ] Run structural inventory on one pinned D-GITT 2023 snapshot.
- [ ] Confirm raw D-GITT is reported as equipment-level with missing steady-state data.
- [ ] Run the scenario workflow on a small reproducible XIIDM fixture with complete
  hypotheses.
- [ ] Run Ruff and the full pytest suite.
- [ ] Update the roadmap with implemented tooling and unresolved scientific evidence.

## Verified Starting Evidence

- Dataset: `OpenSynth/D-GITT-RTE7000-2023`
- Immutable revision: `77bfc432dd505f30a2a2fa79466680b614e3799c`
- Snapshot:
  `2023/01/01/recollement-auto-20230101-0000-enrichi.xiidm.bz2`
- Local SHA-256:
  `aaa51ee8320abee08459076345107117bbe2a4d8aa8f43915fb4fca853fc0127`
- PyPowSyBl verified in the isolated virtualenv: `1.15.0`
- Snapshot inventory observed on 11 June 2026:
  4,856 substations, 5,933 voltage levels, 6,524 bus-view buses, 14,381
  bus/breaker buses, 7,774 lines, 1,803 two-winding transformers, 6,033
  generators, 6,970 loads, and 39,244 operational limits.
- Raw AC load flow is correctly blocked because the network is only valid at the
  equipment level and its steady-state hypotheses are missing.
