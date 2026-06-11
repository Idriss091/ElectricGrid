# Portfolio Screening Geospatial Design

## Objective

Build the first client-usable VoltPath V2 vertical slice: ingest a BESS site portfolio,
discover plausible nearby transmission substations from OpenStreetMap, cross-reference
them with the Cartostock/ODRE/RTE7000 identity layer, and issue an explainable
development-priority ranking.

This release is a `geospatial_screening`, not a network-capacity study. It must not
produce a probability of connection, a firm MW value, or a `go` verdict.

## Chosen Approach

VoltPath will query bounded OSM areas around client sites through Overpass. It will not
download a national OSM extract. Candidates are retained when they are explicitly
associated with RTE or expose a voltage of at least 63 kV.

Two alternatives were rejected for this tranche:

- geocoding every Cartostock row nationally would add a fragile matching pipeline before
  a client site exists;
- downloading a national OSM/OpenInfraMap extract would conflict with the remote,
  selective-access product direction and make assisted screening harder to operate.

## Components

### Portfolio input

The required CSV columns are:

- `client_site_id`;
- `latitude`;
- `longitude`;
- `requested_mw`;
- `storage_duration_hours`.

Optional columns are:

- `land_control_status`;
- `target_connection_date`;
- `max_connection_distance_km`;
- `preferred_voltage_kv`;
- `project_notes`.

The loader rejects duplicate identifiers, missing values, invalid coordinates, and
non-positive power or duration. It reports row-level errors without silently changing
client data.

### OSM substation discovery

The OSM adapter submits one bounded Overpass query per site. It records endpoint,
retrieval timestamp, radius, query, and OSM attribution. Network access is injectable so
tests remain offline.

OSM objects are normalized into:

- OSM type and identifier;
- coordinates;
- name, reference, operator, and voltage tags;
- straight-line distance from the client site;
- source URL and raw matching signals.

Unknown or distribution-only objects are excluded. Geographic proximity remains a
practicality signal and never proves electrical connectivity.

### Identity linking

The link policy is conservative:

1. exact OSM `ref` to ODRE code;
2. unique normalized name plus compatible voltage;
3. unique normalized name when no conflicting voltage evidence exists;
4. otherwise unmatched and flagged for manual review.

No fuzzy name match is silently promoted. A linked identity carries the existing
Cartostock, ODRE, and RTE7000 evidence.

### Screening policy V0

The ranking score is a transparent prioritization index, not a connection probability.
It contains six dimensions required by the commercial objectives:

- connection practicality;
- identity and evidence quality;
- grid attractiveness signal;
- flexible-connection public signal;
- general public-signal completeness;
- client development readiness.

Each dimension is emitted separately with its reason. Missing evidence receives no
positive points and is listed explicitly. The policy version and thresholds are written
to the run manifest so later pilot calibration remains reproducible.

Classes and actions are:

- `A` / `prioritize`: strong geospatial and evidence basis for a Deep Dive shortlist;
- `B` / `investigate`: credible candidate requiring targeted evidence;
- `C` / `hold`: weak or incomplete case;
- `D` / `reject`: no plausible candidate within the accepted search area or invalid
  commercial fit.

Class `A` requires a deterministic canonical identity and RTE7000 link regardless of
raw points. This prevents distance alone from creating a high-confidence result.

### Client deliverables

Each run writes:

- `portfolio_ranked.csv`;
- `candidate_substations.csv`;
- `portfolio_screening_report.md`;
- `portfolio_screening_map.html`;
- `source_assumption_register.json`;
- `run_manifest.json`.

The HTML map is self-contained and uses no client data service. The Markdown report
contains the executive shortlist, per-site rationale, warnings, missing evidence, and
recommended next action.

## Failure Handling

Invalid portfolio data stops the run with actionable row-level messages. A failed OSM
query does not fabricate an empty network: the affected site is marked
`source_unavailable`, receives low evidence confidence, and remains visible in outputs.
Schema changes in Cartostock, ODRE, RTE7000, or OSM raise dedicated errors.

## Testing

Pure unit tests cover CSV validation, distance calculation, OSM filtering, conservative
identity matching, score gates, ranking, and output serialization. CLI integration uses
fixture source data and an injected screening function or local records; live source
access is verified separately and is not required for the unit suite.

## Scientific Boundary

The release supports commercial triage only. Cartostock and CapaReseau are indicative
signals; OSM is geographic context; RTE7000 linkage is reconstructed topology evidence.
Static load flow, time-series risk, contingency analysis, and contractual flexibility
claims enter only after a sufficiently reliable XIIDM node has been selected for a Deep
Dive Site.
