# VoltPath V2 Commercial Product Objectives

## Purpose

VoltPath V1 demonstrated a reproducible method for converting network hosting capacity
into a BESS connection recommendation using SimBench, pandapower, static screening, and
QSTS validation.

VoltPath V2 turns that research prototype into a French commercial pre-feasibility
product. The commercial objective is to help BESS developers avoid spending time,
land-option costs, engineering effort, and development capital on sites with weak or
poorly evidenced connection prospects.

VoltPath V2 remains a buyer-side decision engine. It does not replace an official RTE or
Enedis connection study, a proposition technique et financiere (PTF), or an
operator-issued connection offer.

## Product Transition

SimBench remains the scientific benchmark and regression-validation layer. It is no
longer the primary source for commercial site decisions.

The V2 product must use French public and reconstructed network data to answer:

- which sites in a client portfolio deserve priority;
- which nearby substations are plausible connection candidates;
- what public and reconstructed evidence supports the ranking;
- what constraints or uncertainties could invalidate the opportunity;
- which sites justify a deeper network study or an official connection request.

The product must distinguish observed public facts, reconstructed network evidence,
client-provided facts, and VoltPath assumptions. It must never present a reconstructed
result as operator-validated evidence.

## Commercial Offer Sequence

### 1. Portfolio Screening

Portfolio Screening is the first commercial product and the immediate V2 priority.

The client provides a portfolio of candidate BESS sites. VoltPath ranks the sites by
connection attractiveness, flexible-connection potential, connection practicality,
evidence quality, and development readiness.

The offer is initially delivered as an assisted service. VoltPath runs and reviews the
analysis before issuing client-facing results. A self-service SaaS or partner API is
outside the first commercial release.

Portfolio Screening must help a client decide:

- which sites to prioritize;
- which sites require additional evidence;
- which sites to hold;
- which sites to reject before further development spending;
- which top sites should proceed to a Deep Dive Site analysis.

### 2. Deep Dive Site

Deep Dive Site is the premium follow-on offer for a small number of serious candidates.

It uses a more detailed XIIDM network model, reconstructed operating states, PyPowSyBl
network calculations, scenario analysis, and the existing VoltPath risk and economic
decision logic.

Its purpose is to support a decision before an official connection request, material
engineering expenditure, or final land commitment. It remains pre-feasibility and must
not claim to reproduce a PTF.

### 3. Site Finder / Zone Finder

Site Finder is a later product. It identifies promising prospecting zones for clients
that do not yet own or control candidate sites.

It must not be launched as a national "available capacity map" until:

- the French substation identity model is reliable;
- geographic matching quality is measured;
- Portfolio Screening has been tested with real client portfolios;
- Deep Dive results have been used to calibrate screening false positives;
- public signals and reconstructed calculations can be explained consistently.

Site Finder will recommend areas for further land and grid investigation, not specific
parcels with guaranteed connection capacity.

## Mandatory V2 Data and Modeling Stack

### Cartostock

Cartostock is the initial commercial-shortlist and public-context source.

It provides substation identifiers and public signals such as:

- capacity-without-constraint categories;
- TURPE injection or withdrawal zones;
- storage gabarit information;
- capacity associated with a post or gabarit zone;
- nearby-demand indicators where available.

Cartostock fields are indicative public signals. They are not guaranteed connection
capacity and are not sufficient for a physical network conclusion.

### RTE7000 and D-GITT

RTE7000 and D-GITT provide the reconstructed French transmission-network topology.

- `OpenSynth/rte7000` is the preferred tabular source for portfolio-scale screening.
- D-GITT XIIDM snapshots are reserved for targeted Deep Dive analyses and validation.
- Reconstructed load, generation, substation, and geographic mappings must retain their
  source method and uncertainty.
- Heuristic substation matches must never be silently treated as exact.

### PyPowSyBl and XIIDM

PyPowSyBl is the primary V2 network-analysis engine for French XIIDM models.

The intended capabilities are:

- AC and DC load flow;
- network variants and scenario evaluation;
- active-power injection and withdrawal tests;
- sensitivity analysis;
- security and contingency analysis when the model supports it;
- extraction of voltage, loading, convergence, and binding-constraint evidence.

Every run must record the PyPowSyBl version, load-flow provider, solver parameters,
network source revision, and scenario assumptions.

### ODRE and RTE Data

ODRE and RTE public data provide time-series and system-context evidence, including:

- regional and national consumption;
- generation by technology;
- pumping and battery-storage signals where available;
- regional exchanges;
- consolidated, definitive, and real-time data distinctions.

Public regional series may be used to reconstruct operating scenarios. They must not be
described as measured nodal injections unless the source explicitly provides that level
of evidence.

### CapaReseau

CapaReseau is a complementary indicative signal.

It may enrich ranking and interpretation, but it must not override network calculations
or be presented as guaranteed BESS connection capacity. Its scope, publication date,
voltage level, and production-oriented context must remain visible in reports.

### OpenStreetMap and OpenInfraMap

OpenStreetMap and OpenInfraMap provide geographic and infrastructure context:

- coordinates and visible substations;
- nearby transmission corridors;
- straight-line and route-proxy distances;
- geographic context for connection practicality.

They are not authoritative sources for network limits, bay availability, thermal
ratings, electrical connectivity, or official substation capacity.

## Remote Hugging Face Data Access

VoltPath must not clone or download the complete RTE7000 or D-GITT datasets as part of
the normal workflow.

The implementation must:

- read Hugging Face-hosted Parquet partitions remotely;
- select only the required component, year, month, columns, and rows;
- use streaming or remote filesystem access where practical;
- pin datasets to a repository commit SHA or immutable revision;
- permit a bounded, disposable local cache for fetched fragments;
- record every accessed partition in the run manifest;
- fail clearly when the remote source is unavailable or its schema changes.

D-GITT XIIDM files must be retrieved individually for selected Deep Dive timestamps or
scenarios. A full D-GITT mirror is outside the product workflow.

Client-facing reproducibility requires the dataset revision, file paths, query scope,
and transformation version to be recorded for every result.

## French Substation Identity

A reliable cross-source substation identity layer is a prerequisite for commercial
claims.

The canonical record must be capable of linking:

- Cartostock identifiers;
- RTE7000 and XIIDM identifiers;
- ODRE substation records;
- OpenStreetMap or OpenInfraMap objects;
- commune and INSEE identifiers;
- coordinates and voltage levels.

Every match must expose its method and confidence:

- `exact`;
- `high`;
- `medium`;
- `low`;
- `unmatched`.

Low-confidence or ambiguous matches must reduce the evidence score and trigger manual
review. They must not produce an apparently precise nodal-capacity conclusion.

## Portfolio Screening Input Contract

The minimum client input is a CSV or equivalent structured table containing:

- `client_site_id`;
- `latitude`;
- `longitude`;
- `requested_mw`;
- `storage_duration_hours`.

Optional inputs include:

- land-control status;
- target connection date;
- maximum acceptable connection distance;
- preferred voltage level;
- project notes;
- known planning, environmental, or access constraints.

Coordinates and project values must be validated before analysis. Invalid, duplicate,
or ambiguous sites must be reported rather than silently corrected.

## Portfolio Screening Analysis

The screening workflow must:

1. identify plausible nearby substations and network corridors;
2. link those substations to the canonical French substation identity;
3. attach Cartostock, TURPE, gabarit, and CapaReseau signals;
4. attach RTE7000 topology and electrical attributes;
5. attach ODRE/RTE regional operating-context indicators;
6. estimate connection distance and geographic practicality;
7. run only the level of network calculation justified by the available evidence;
8. rank sites with an explainable score and explicit uncertainty;
9. recommend the next action for every site.

The score must cover at least:

- grid attractiveness;
- flexible-connection potential;
- connection practicality;
- public-signal strength;
- evidence quality;
- client-provided development readiness.

The scoring model must not output an unsupported numerical probability of successful
connection. Initial results should use transparent classes and recommendations.

## Portfolio Screening Outputs

Each site must receive:

- portfolio rank;
- `A`, `B`, `C`, or `D` opportunity class;
- `prioritize`, `investigate`, `hold`, or `reject` recommendation;
- plausible candidate substations;
- assumed connection voltage and distance;
- strongest positive signals;
- likely constraints;
- missing evidence;
- match and evidence confidence;
- recommended next action.

The client delivery must include:

- an executive report;
- the complete ranked portfolio in a machine-readable format;
- a map of sites and candidate substations;
- detailed cards for the leading candidates;
- a source, assumption, and uncertainty register;
- a recommended Deep Dive shortlist.

Portfolio Screening must not use the V1 `go` verdict as if it represented annual network
feasibility. `go`, `go-with-conditions`, and `no-go` remain reserved for a sufficiently
deep network assessment. Screening recommendations describe development priority, not
official feasibility.

## Evidence Levels and Commercial Language

V2 reports must identify both the evidence source and the validation depth.

Evidence-source categories:

- `benchmark`: SimBench or equivalent benchmark evidence;
- `public_signal`: Cartostock, CapaReseau, or similar published indication;
- `public_reconstruction`: RTE7000, D-GITT-derived, ODRE-derived, or heuristic French
  reconstruction;
- `client_model`: network or operating data supplied by a client or consultant;
- `operator_validated`: only when the relevant model and assumptions have been
  explicitly validated through an operator or official process.

Validation-depth categories:

- `geospatial_screening`;
- `topology_screening`;
- `static_load_flow`;
- `sampled_time_series`;
- `full_year_time_series`;
- `security_analysis`.

Confidence must reflect both dimensions. More computation must not create high
confidence when the source data or substation match is weak.

Required commercial warnings:

- results are buyer-side pre-feasibility evidence;
- public capacity signals are not reservations or guarantees;
- reconstructed injections are not operator measurements;
- geographic proximity does not prove electrical connectability;
- official cost, delay, protection, short-circuit, stability, land, and bay-availability
  conclusions require further study;
- RTE or Enedis remains responsible for the official connection process.

## Portfolio Screening Success Criteria

The first commercial release is successful when it can:

- process a portfolio of 100 valid sites within two working days as an assisted service;
- produce a reproducible and explainable ranking;
- identify a small actionable shortlist for client review;
- show the evidence and uncertainty behind every recommendation;
- prevent unsupported capacity or feasibility claims;
- convert at least one shortlisted site per pilot portfolio into a Deep Dive discussion;
- collect enough client feedback to measure false positives, false negatives, and
  willingness to pay.

Technical acceptance requires:

- pinned and reproducible remote datasets;
- deterministic transformations for a fixed manifest;
- tested source-schema validation;
- explicit substation-match confidence;
- no cross-client data leakage;
- graceful handling of missing sources and network failures;
- traceable score versions and assumptions.

## Pilot Roadmap

### Stage 1: Data foundation

- implement remote, revision-pinned access to selected RTE7000 Parquet partitions;
- catalogue Cartostock and ODRE fields used by the product;
- define source licenses, update dates, and provenance metadata;
- validate that no normal workflow requires a complete dataset download.

### Stage 2: Substation identity

- normalize names, identifiers, communes, coordinates, and voltage levels;
- produce confidence-scored cross-source matches;
- manually review a representative set of important French substations;
- measure matching coverage and ambiguity.

### Stage 3: Assisted Portfolio Screening

- accept the minimum client input contract;
- calculate geographic, public-signal, topology, and evidence-quality features;
- produce a first explainable ranking and report;
- review every client result before delivery.

### Stage 4: Pilot calibration

- run three to five pilot portfolios containing approximately 20 to 100 sites each;
- compare VoltPath ranking with client internal views and subsequent site decisions;
- record promoted, rejected, and later-invalidated candidates;
- calibrate score thresholds without hiding uncertainty.

### Stage 5: Deep Dive integration

- retrieve selected XIIDM snapshots remotely;
- run PyPowSyBl scenarios on shortlisted sites;
- reuse the existing VoltPath capacity, curtailment, resize, economic, and decision
  concepts where scientifically compatible;
- compare screening recommendations against deeper network evidence.

### Stage 6: Site Finder decision

- assess whether the calibrated data supports a geographic prospecting product;
- launch only if substation matching, distance interpretation, and screening precision
  are sufficient for defensible zone recommendations.

## Development Gate

This document is the V2 product-direction gate.

No V2 implementation should begin until the product owner has reviewed and accepted:

- the commercial offer sequence;
- the mandatory stack;
- remote Hugging Face access constraints;
- the Portfolio Screening input and output contract;
- the evidence language and prohibited claims;
- the pilot success criteria.

Future implementation plans must reference this document and must not silently broaden
the product into a generic digital twin, official connection-study substitute, or
unvalidated national capacity map.
