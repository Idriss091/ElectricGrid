# Portfolio Screening V2

## Purpose

`portfolio-screen` ranks a client portfolio of French BESS sites using:

- Cartostock public commercial signals;
- ODRE substation identity data;
- a remotely projected and timestamp-filtered RTE7000 `sub` partition;
- bounded OpenStreetMap/Overpass substation queries;
- the versioned `portfolio-geospatial-v1` policy.

The command produces development priorities, not connection-capacity guarantees. It does
not run PyPowSyBl or issue a `go` verdict. Those deeper calculations belong to a selected
Deep Dive Site after manual node validation.

## Client CSV

Required columns:

```text
client_site_id,latitude,longitude,requested_mw,storage_duration_hours
```

Optional columns:

```text
land_control_status,target_connection_date,max_connection_distance_km,
preferred_voltage_kv,project_notes
```

Coordinates, duplicate identifiers, positive power, duration, and optional numeric
values are validated before any source access.

## Live Command

Use an immutable Hugging Face commit SHA:

```bash
PYTHONPATH=src python -m thesegrid.cli portfolio-screen \
  --portfolio examples/portfolio_sites.csv \
  --cartostock cartostock/postes_cartostock.csv \
  --output results/portfolio-screening-live \
  --rte7000-revision 1a2419a6f8a81ab212af035e811d4b893d7c4ccf \
  --rte7000-year 2023 \
  --rte7000-month 1 \
  --rte7000-snapshot 2023-01-01T00:00:00 \
  --search-radius-km 50 \
  --odre-substations ODRE/postes-electriques-rte.csv \
  --odre-constraints ODRE/contraintes-region.csv \
  --odre-storage-assets ODRE/registre-national-installation-production-stockage-electricite-agrege.csv \
  --odre-regional-loads ODRE/soutirages-regionaux-quotidiens-provisoires-rpt.csv \
  --eco2mix-annual ECO2MIX/eCO2mix_RTE_Annuel-Definitif_2024.xls
```

The RTE7000 reader requests only:

- `sub/sub_2023-01.parquet`;
- columns `id` and `name`;
- rows matching the selected timestamp.

It does not clone or download the complete dataset.

`--odre-substations` pins identity matching to a local ODRE snapshot. The exact file
hash, file date, read date, publisher, licence, and transformation version are recorded
in the run manifest. Omitting the option still permits the live ODRE export, but that
mode is less reproducible.

## Reproducible Demo

The OSM fixture avoids live Overpass variability while retaining the production parser:

```bash
PYTHONPATH=src python -m thesegrid.cli portfolio-screen \
  --portfolio examples/portfolio_sites.csv \
  --cartostock cartostock/postes_cartostock.csv \
  --output results/portfolio-screening-demo \
  --rte7000-revision 1a2419a6f8a81ab212af035e811d4b893d7c4ccf \
  --odre-substations ODRE/postes-electriques-rte.csv \
  --osm-fixture examples/osm_jalis_fixture.json
```

ODRE and the projected RTE7000 snapshot remain live remote sources. The OSM fixture is
hashed and recorded in the run manifest.

Local ODRE and ECO2MIX paths are optional. When provided, they enrich the ranking with
public-context evidence:

- regional constraint count, duration, occurrence, and persistence;
- BESS/storage density by region and matched source substation;
- latest available regional withdrawal date;
- national ECO2MIX system-context coverage.

These signals improve prioritization and Deep Dive shortlisting. They are not nodal
measurements, reserved capacity, or official connection feasibility.

ECO2MIX annual exports are interpreted at their actual timestamp cadence. The normalized
data distinguishes:

- source records, usually at a 15-minute cadence;
- observed consumption measurements;
- forecast-only or otherwise missing measurement rows;
- covered hours computed from records multiplied by cadence.

Missing measurements remain null. They are never silently converted to zero.

## Mandatory Class A Review

Every Class A result requires human review before it can become a `recommended` Deep
Dive. Without a review file it remains `conditional` and appears in
`manual_review_queue.csv`.

An optional review CSV uses:

```text
client_site_id,status,reviewer,reviewed_at_utc,notes
SITE-01,approved,A. Expert,2026-06-11T12:00:00+00:00,Identity and voltage checked
SITE-02,rejected,A. Expert,2026-06-11T12:15:00+00:00,Voltage conflict
```

Pass it with `--manual-reviews path/to/manual_reviews.csv`. Accepted statuses are
`approved` and `rejected`; reviewer and timezone-aware review timestamp are mandatory.

## Outputs

- `portfolio_ranked.csv`: one commercial decision row per client site;
- `candidate_substations.csv`: full candidate and identity audit trail;
- `public_grid_evidence.csv`: ODRE/ECO2MIX-derived public-context evidence per linked
  site/candidate profile;
- `deep_dive_shortlist.csv`: directly actionable list of sites recommended or
  conditionally recommended for Deep Dive scoping;
- `deep_dive_inputs/`: one JSON preparation package per shortlisted site, including
  site demand, candidate substation identifiers, public evidence, score rationale,
  manual validation checklist, and prohibited claims;
- `site_finder_seed_signals.csv`: deduplicated reference-substation signals from
  shortlisted sites for a later Site Finder workflow;
- `portfolio_bundle_summary.json`: machine-readable run summary with class counts,
  Deep Dive counts, source-error count, and top-ranked site;
- `portfolio_screening_report.md`: executive shortlist and detailed rationale;
- `portfolio_screening_map.html`: standalone relative-location map;
- `source_assumption_register.json`: source roles, assumptions, and prohibited claims;
- `manual_review_queue.csv`: Class A review status and evidence needed before approval;
- `data_quality_report.json`: source traceability, ECO2MIX cadence and missingness,
  identity confidence, source errors, and Class A delivery gate;
- `run_manifest.json`: policy, timestamps, source revisions, hashes, errors, and outputs.

## Interpretation

- `A / prioritize`: strong geospatial and evidence basis for Deep Dive scoping;
- `B / investigate`: credible site with targeted evidence gaps;
- `C / hold`: insufficient or weak evidence;
- `D / reject`: no candidate or candidate outside the client's practical limit.

Class A requires both a deterministic canonical identity and an RTE7000 topology link.
It also remains conditional until the mandatory human review is approved.
No numerical score is a probability of successful connection.

`deep_dive_recommendation` is a shortlist trigger:

- `recommended`: Class A candidate with substantial public evidence coverage;
- `conditional`: promising candidate that still needs manual source or identity review;
- `not_recommended`: weak, rejected, or insufficiently evidenced candidate.

Files under `deep_dive_inputs/` are handoff packages for a later Deep Dive workflow.
They preserve the screening evidence and manual validation checklist but do not contain
power-flow results, hosting capacity, curtailment estimates, or a connection verdict.

`site_finder_seed_signals.csv` is a preparation artifact only. It identifies public
reference-substation signals worth reusing in a future Site Finder workflow; it does not
generate prospecting zones, land parcels, or new site recommendations.

## Known Boundaries

- OSM voltage values are interpreted according to the OSM convention: volts without a
  unit, with semicolon-separated levels.
- Existing batteries in a region or at a source substation remain contextual evidence
  and contribute no scoring points under `portfolio-geospatial-v1`.
- Geographic distance is straight-line distance, not a cable route or land-access study.
- Cartostock gabarits are indicative injection signals and may not describe a symmetric
  BESS operating envelope.
- RTE7000 is a public reconstruction and is not operator-validated.
- Official feasibility, cost, delay, protection, stability, short-circuit, land, and
  bay-availability conclusions require further study and the RTE/Enedis process.
