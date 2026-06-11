# V2 Public Evidence Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Portfolio Screening so a client CSV produces a ranked BESS portfolio enriched with ODRE/ECO2MIX public evidence and a Deep Dive shortlist trigger.

**Architecture:** Add a focused `thesegrid.public_data` package for local source ingestion and evidence aggregation. Keep source parsing separate from portfolio scoring; integrate only normalized `PublicGridEvidenceProfile` records into existing portfolio ranking and reporting.

**Tech Stack:** Typed Python, dataclasses, pandas, pathlib, hashlib, csv, pytest, ruff, existing VoltPath portfolio modules.

---

### Task 1: Public Data Package Skeleton And Manifests

**Files:**
- Create: `src/thesegrid/public_data/__init__.py`
- Create: `src/thesegrid/public_data/sources.py`
- Create: `tests/test_public_data_sources.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from thesegrid.public_data.sources import LocalSourceManifest, local_source_manifest


def test_local_source_manifest_records_hash_size_and_role(tmp_path: Path):
    source = tmp_path / "sample.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    manifest = local_source_manifest(source, source_type="odre_constraints")

    assert isinstance(manifest, LocalSourceManifest)
    assert manifest.path == source
    assert manifest.source_type == "odre_constraints"
    assert manifest.size_bytes == source.stat().st_size
    assert len(manifest.sha256) == 64
    assert manifest.available is True
    assert manifest.error == ""


def test_missing_local_source_manifest_is_non_available(tmp_path: Path):
    manifest = local_source_manifest(tmp_path / "missing.csv", source_type="eco2mix")

    assert manifest.available is False
    assert manifest.size_bytes == 0
    assert manifest.sha256 == ""
    assert "missing" in manifest.error
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_public_data_sources.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'thesegrid.public_data'`.

- [ ] **Step 3: Implement the minimal source manifest API**

Create `src/thesegrid/public_data/__init__.py`:

```python
"""Public data ingestion and evidence helpers for VoltPath V2."""
```

Create `src/thesegrid/public_data/sources.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalSourceManifest:
    path: Path
    source_type: str
    available: bool
    size_bytes: int
    sha256: str
    error: str = ""


def local_source_manifest(path: Path, source_type: str) -> LocalSourceManifest:
    if not path.exists():
        return LocalSourceManifest(
            path=path,
            source_type=source_type,
            available=False,
            size_bytes=0,
            sha256="",
            error=f"missing local source: {path}",
        )
    payload = path.read_bytes()
    return LocalSourceManifest(
        path=path,
        source_type=source_type,
        available=True,
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(payload).hexdigest(),
    )
```

- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/test_public_data_sources.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/thesegrid/public_data/__init__.py src/thesegrid/public_data/sources.py tests/test_public_data_sources.py
git commit -m "feat: add public data source manifests"
```

### Task 2: ODRE Local Loaders

**Files:**
- Create: `src/thesegrid/public_data/odre.py`
- Create: `tests/test_public_data_odre.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import pandas as pd
import pytest

from thesegrid.public_data.odre import (
    OdreSchemaError,
    read_regional_constraints,
    read_storage_assets,
)


def test_read_regional_constraints_handles_bom_and_required_columns(tmp_path: Path):
    path = tmp_path / "contraintes-region.csv"
    path.write_text(
        "\ufeffRégion,Ouvrage,Nom de l'ouvrage,Puissance max de l'ouvrage,"
        "Poste 1,Pourcentage 1,Occurrence,Durée,Pérennité,Specificité\n"
        "GRAND EST,ABC,LIAISON ABC,50.0,POSTE,-40.0,"
        "Forte : entre 75 et 150 fois par an,]2h-4h],ELEVEE,Contrainte en journée\n",
        encoding="utf-8",
    )

    result = read_regional_constraints(path)

    assert len(result.frame) == 1
    assert result.frame.loc[0, "region"] == "GRAND EST"
    assert result.frame.loc[0, "persistence"] == "ELEVEE"
    assert result.manifest.available is True


def test_read_regional_constraints_rejects_schema_drift(tmp_path: Path):
    path = tmp_path / "contraintes-region.csv"
    path.write_text("Région,Ouvrage\nGRAND EST,ABC\n", encoding="utf-8")

    with pytest.raises(OdreSchemaError, match="missing columns"):
        read_regional_constraints(path)


def test_read_storage_assets_normalizes_battery_rows(tmp_path: Path):
    path = tmp_path / "registre.csv"
    pd.DataFrame(
        [
            {
                "region": "Bretagne",
                "posteSource": "BRETA",
                "filiere": "Stockage non hydraulique",
                "typeStockage": "BATTE",
                "tensionRaccordement": "HTA",
                "puisMaxInstallee": "1200",
                "puisMaxCharge": "1000",
                "puisMaxInstalleeDisCharge": "1000",
                "energieStockable": "2400",
                "nbInstallations": "1",
            }
        ]
    ).to_csv(path, index=False)

    result = read_storage_assets(path)

    row = result.frame.iloc[0]
    assert row["region"] == "Bretagne"
    assert row["source_substation"] == "BRETA"
    assert row["is_battery"] is True
    assert row["installed_kw"] == 1200.0
    assert row["stockable_kwh"] == 2400.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_public_data_odre.py -v`

Expected: FAIL with missing `thesegrid.public_data.odre`.

- [ ] **Step 3: Implement ODRE loaders**

Implement:

```python
class OdreSchemaError(ValueError): ...

@dataclass(frozen=True)
class OdreTable:
    frame: pd.DataFrame
    manifest: LocalSourceManifest

def read_regional_constraints(path: Path) -> OdreTable: ...
def read_storage_assets(path: Path) -> OdreTable: ...
```

Required behavior:

- read with `encoding="utf-8-sig"`;
- validate required raw columns;
- rename to snake-case product columns;
- parse numeric columns with comma-to-dot normalization;
- set `is_battery` when `typeStockage == "BATTE"`;
- attach `local_source_manifest`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_public_data_odre.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/thesegrid/public_data/odre.py tests/test_public_data_odre.py
git commit -m "feat: load ODRE public evidence sources"
```

### Task 3: ECO2MIX TSV Loaders

**Files:**
- Create: `src/thesegrid/public_data/eco2mix.py`
- Create: `tests/test_public_data_eco2mix.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import pytest

from thesegrid.public_data.eco2mix import Eco2mixSchemaError, read_eco2mix_annual, read_tempo_days


def test_read_eco2mix_annual_accepts_tsv_with_xls_extension(tmp_path: Path):
    path = tmp_path / "eCO2mix.xls"
    path.write_text(
        "Périmètre\tNature\tDate\tHeures\tConsommation\tSolaire\tEolien\t Stockage batterie\tDéstockage batterie\n"
        "France\tDonnées définitives\t2024-01-01\t00:00\t55000\t0\t15557\t0\t14976\n",
        encoding="latin1",
    )

    result = read_eco2mix_annual(path)

    row = result.frame.iloc[0]
    assert str(row["timestamp"]) == "2024-01-01 00:00:00"
    assert row["consumption_mw"] == 55000.0
    assert row["battery_discharge_mw"] == 14976.0


def test_read_tempo_days_drops_rte_notice_line(tmp_path: Path):
    path = tmp_path / "tempo.xls"
    path.write_text(
        "Date\tType de jour TEMPO\n"
        "2024-09-01\tBLEU\n"
        "L'ensemble des informations disponibles sur éCO2mix sont fournies à titre informatif\t\n",
        encoding="utf-8",
    )

    result = read_tempo_days(path)

    assert len(result.frame) == 1
    assert result.frame.loc[0, "tempo_day_type"] == "BLEU"


def test_read_eco2mix_annual_rejects_missing_columns(tmp_path: Path):
    path = tmp_path / "bad.xls"
    path.write_text("Date\tConsommation\n2024-01-01\t1\n", encoding="utf-8")

    with pytest.raises(Eco2mixSchemaError, match="missing columns"):
        read_eco2mix_annual(path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_public_data_eco2mix.py -v`

Expected: FAIL with missing `thesegrid.public_data.eco2mix`.

- [ ] **Step 3: Implement ECO2MIX loaders**

Implement:

```python
class Eco2mixSchemaError(ValueError): ...

@dataclass(frozen=True)
class Eco2mixTable:
    frame: pd.DataFrame
    manifest: LocalSourceManifest

def read_eco2mix_annual(path: Path) -> Eco2mixTable: ...
def read_tempo_days(path: Path) -> Eco2mixTable: ...
```

Required behavior:

- read annual file as tab-separated text, first with `latin1`, then fallback `utf-8`;
- combine `Nature` date and `Date` hour into a timestamp for current RTE export shape;
- parse numeric columns defensively;
- read Tempo file as UTF-8 TSV;
- drop non-date RTE notice rows;
- attach `local_source_manifest`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_public_data_eco2mix.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/thesegrid/public_data/eco2mix.py tests/test_public_data_eco2mix.py
git commit -m "feat: load ECO2MIX public context sources"
```

### Task 4: Public Grid Evidence Profiles

**Files:**
- Create: `src/thesegrid/public_data/evidence.py`
- Create: `tests/test_public_grid_evidence.py`

- [ ] **Step 1: Write the failing tests**

```python
import pandas as pd

from thesegrid.public_data.evidence import build_public_grid_evidence


def test_build_public_grid_evidence_aggregates_region_and_battery_signals():
    constraints = pd.DataFrame(
        [
            {"region": "BRETAGNE", "occurrence": "Forte", "duration": "]2h-4h]", "persistence": "ELEVEE"},
            {"region": "BRETAGNE", "occurrence": "Faible", "duration": "]0h-2h]", "persistence": "MOYENNE"},
        ]
    )
    storage = pd.DataFrame(
        [
            {
                "region": "BRETAGNE",
                "source_substation": "BRETA",
                "is_battery": True,
                "installed_kw": 1200.0,
                "stockable_kwh": 2400.0,
            }
        ]
    )

    profiles = build_public_grid_evidence(
        site_candidates=[{"client_site_id": "S1", "region": "BRETAGNE", "odre_code": "BRETA"}],
        regional_constraints=constraints,
        storage_assets=storage,
        regional_load_profiles=None,
        eco2mix_annual=None,
    )

    profile = profiles[0]
    assert profile.client_site_id == "S1"
    assert profile.regional_constraint_count == 2
    assert profile.high_persistence_constraint_count == 1
    assert profile.battery_storage_kw_region == 1200.0
    assert profile.battery_storage_kw_source_substation == 1200.0
    assert profile.source_completeness_score > 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_public_grid_evidence.py -v`

Expected: FAIL with missing `thesegrid.public_data.evidence`.

- [ ] **Step 3: Implement evidence aggregation**

Implement a frozen `PublicGridEvidenceProfile` dataclass and `build_public_grid_evidence`.

Required fields:

```python
client_site_id: str
region: str
odre_code: str
regional_constraint_count: int
dominant_constraint_occurrence: str
dominant_constraint_duration: str
high_persistence_constraint_count: int
battery_storage_kw_region: float
battery_storage_kwh_region: float
battery_storage_kw_source_substation: float
latest_regional_load_date: str
eco2mix_coverage_hours: int
source_completeness_score: float
missing_evidence: tuple[str, ...]
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_public_grid_evidence.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/thesegrid/public_data/evidence.py tests/test_public_grid_evidence.py
git commit -m "feat: build public grid evidence profiles"
```

### Task 5: Portfolio Screening Integration

**Files:**
- Modify: `src/thesegrid/portfolio_screening.py`
- Modify: `src/thesegrid/portfolio_workflow.py`
- Modify: `src/thesegrid/cli.py`
- Modify: `tests/test_portfolio_screening.py`
- Modify: `tests/test_portfolio_workflow.py`
- Modify: `tests/test_assessment_and_cli.py`

- [ ] **Step 1: Write failing integration tests**

Add tests asserting:

```python
def test_portfolio_screening_uses_public_grid_evidence_in_score_and_explanation():
    ...
    assert result.sites[0].best_candidate.public_evidence.regional_constraint_count == 2
    assert "public_grid_evidence" in result.sites[0].best_candidate.score_dimensions_by_name
    assert result.sites[0].deep_dive_recommendation in {"recommended", "conditional"}
```

Add CLI/workflow tests asserting ODRE/ECO2MIX optional paths are accepted and missing paths degrade evidence rather than crashing.

- [ ] **Step 2: Run focused tests and confirm failure**

Run:

```bash
pytest tests/test_portfolio_screening.py tests/test_portfolio_workflow.py tests/test_assessment_and_cli.py -v
```

Expected: FAIL because public evidence fields and CLI options do not exist.

- [ ] **Step 3: Extend request and workflow objects**

Add optional paths to `PortfolioWorkflowRequest` and CLI:

```python
odre_constraints_path: Path | None = None
odre_storage_assets_path: Path | None = None
eco2mix_annual_path: Path | None = None
```

Read available sources, build `PublicGridEvidenceProfile` rows after identity linking, and pass profiles into `screen_portfolio`.

- [ ] **Step 4: Extend scoring deterministically**

Add a seventh score dimension named `public_grid_evidence` with bounded points:

- positive points for source completeness;
- positive context for strong storage/gabarit public evidence;
- negative or zero contribution for missing evidence;
- no override of Class A identity and RTE7000 gate.

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_portfolio_screening.py tests/test_portfolio_workflow.py tests/test_assessment_and_cli.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/thesegrid/portfolio_screening.py src/thesegrid/portfolio_workflow.py src/thesegrid/cli.py tests/test_portfolio_screening.py tests/test_portfolio_workflow.py tests/test_assessment_and_cli.py
git commit -m "feat: enrich portfolio screening with public grid evidence"
```

### Task 6: Reporting And Deep Dive Shortlist

**Files:**
- Modify: `src/thesegrid/portfolio_reporting.py`
- Modify: `tests/test_portfolio_reporting.py`
- Modify: `docs/portfolio-screening.md`

- [ ] **Step 1: Write failing reporting tests**

Add tests asserting:

```python
def test_portfolio_outputs_include_public_grid_evidence_and_deep_dive_shortlist(tmp_path):
    ...
    assert (tmp_path / "public_grid_evidence.csv").exists()
    assert "Recommended Deep Dive Shortlist" in report_markdown
    assert "ODRE and ECO2MIX are public-context evidence" in report_markdown
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `pytest tests/test_portfolio_reporting.py -v`

Expected: FAIL because `public_grid_evidence.csv` and report section do not exist.

- [ ] **Step 3: Implement deliverables**

Write:

- `public_grid_evidence.csv`;
- public evidence columns in ranked/candidate CSVs;
- report section for ODRE/ECO2MIX limits;
- `deep_dive_recommendation` and shortlist table.

- [ ] **Step 4: Update documentation**

Update `docs/portfolio-screening.md` with:

- new optional local data flags;
- output list;
- interpretation of public-evidence fields;
- explicit warning that ODRE/ECO2MIX are not nodal capacity measurements.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_portfolio_reporting.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/thesegrid/portfolio_reporting.py tests/test_portfolio_reporting.py docs/portfolio-screening.md
git commit -m "feat: report public evidence and deep dive shortlist"
```

### Task 7: End-To-End Verification

**Files:**
- Modify only files required by failures attributable to this tranche.

- [ ] **Step 1: Run public data tests**

Run:

```bash
pytest tests/test_public_data_sources.py tests/test_public_data_odre.py tests/test_public_data_eco2mix.py tests/test_public_grid_evidence.py -v
```

Expected: PASS.

- [ ] **Step 2: Run portfolio tests**

Run:

```bash
pytest tests/test_portfolio_input.py tests/test_portfolio_screening.py tests/test_portfolio_reporting.py tests/test_portfolio_workflow.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run: `pytest`

Expected: PASS.

- [ ] **Step 4: Run lint**

Run: `ruff check .`

Expected: `All checks passed!`

- [ ] **Step 5: Run the local enriched demo**

Run:

```bash
PYTHONPATH=src python -m thesegrid.cli portfolio-screen \
  --portfolio examples/portfolio_sites.csv \
  --cartostock cartostock/postes_cartostock.csv \
  --output results/portfolio-screening-v2-demo \
  --rte7000-revision 1a2419a6f8a81ab212af035e811d4b893d7c4ccf \
  --osm-fixture examples/osm_jalis_fixture.json \
  --odre-constraints ODRE/contraintes-region.csv \
  --odre-storage-assets ODRE/registre-national-installation-production-stockage-electricite-agrege.csv \
  --eco2mix-annual ECO2MIX/eCO2mix_RTE_Annuel-Definitif_2024.xls
```

Expected outputs:

- `results/portfolio-screening-v2-demo/portfolio_ranked.csv`;
- `results/portfolio-screening-v2-demo/candidate_substations.csv`;
- `results/portfolio-screening-v2-demo/public_grid_evidence.csv`;
- `results/portfolio-screening-v2-demo/portfolio_screening_report.md`;
- `results/portfolio-screening-v2-demo/run_manifest.json`.

- [ ] **Step 6: Inspect prohibited claims**

Run:

```bash
rg -n "guaranteed|official capacity|PTF replacement|probability of connection" results/portfolio-screening-v2-demo
```

Expected: no unsupported commercial claims.

- [ ] **Step 7: Commit verification fixes if needed**

```bash
git add <files changed to fix verification failures>
git commit -m "test: verify v2 public evidence ranking workflow"
```
