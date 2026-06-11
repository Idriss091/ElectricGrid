# Portfolio Screening V2

## Purpose

`portfolio-screen` ranks a client portfolio of French BESS sites using:

- Cartostock public commercial signals;
- ODRE substation identity data;
- a remotely projected and timestamp-filtered RTE7000 `sub` partition;
- bounded OpenStreetMap/Overpass substation queries;
- the versioned `portfolio-geospatial-v0` policy.

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
  --search-radius-km 50
```

The RTE7000 reader requests only:

- `sub/sub_2023-01.parquet`;
- columns `id` and `name`;
- rows matching the selected timestamp.

It does not clone or download the complete dataset.

## Reproducible Demo

The OSM fixture avoids live Overpass variability while retaining the production parser:

```bash
PYTHONPATH=src python -m thesegrid.cli portfolio-screen \
  --portfolio examples/portfolio_sites.csv \
  --cartostock cartostock/postes_cartostock.csv \
  --output results/portfolio-screening-demo \
  --rte7000-revision 1a2419a6f8a81ab212af035e811d4b893d7c4ccf \
  --osm-fixture examples/osm_jalis_fixture.json
```

ODRE and the projected RTE7000 snapshot remain live remote sources. The OSM fixture is
hashed and recorded in the run manifest.

## Outputs

- `portfolio_ranked.csv`: one commercial decision row per client site;
- `candidate_substations.csv`: full candidate and identity audit trail;
- `portfolio_screening_report.md`: executive shortlist and detailed rationale;
- `portfolio_screening_map.html`: standalone relative-location map;
- `source_assumption_register.json`: source roles, assumptions, and prohibited claims;
- `run_manifest.json`: policy, timestamps, source revisions, hashes, errors, and outputs.

## Interpretation

- `A / prioritize`: strong geospatial and evidence basis for Deep Dive scoping;
- `B / investigate`: credible site with targeted evidence gaps;
- `C / hold`: insufficient or weak evidence;
- `D / reject`: no candidate or candidate outside the client's practical limit.

Class A requires both a deterministic canonical identity and an RTE7000 topology link.
No numerical score is a probability of successful connection.

## Known Boundaries

- OSM voltage values are interpreted according to the OSM convention: volts without a
  unit, with semicolon-separated levels.
- Geographic distance is straight-line distance, not a cable route or land-access study.
- Cartostock gabarits are indicative injection signals and may not describe a symmetric
  BESS operating envelope.
- RTE7000 is a public reconstruction and is not operator-validated.
- Official feasibility, cost, delay, protection, stability, short-circuit, land, and
  bay-availability conclusions require further study and the RTE/Enedis process.
