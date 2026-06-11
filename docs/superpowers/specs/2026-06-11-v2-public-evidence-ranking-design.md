# V2 Public Evidence Ranking Design

## Objective

Extend VoltPath V2 Portfolio Screening so a client can provide a BESS site list and receive
an explainable ranking enriched with local ODRE and ECO2MIX evidence, while preserving the
current product boundary: buyer-side pre-feasibility, not an official connection study or a
national available-capacity map.

This tranche upgrades the existing geospatial screening workflow. It does not implement
PyPowSyBl Deep Dive calculations or Site Finder generation, but it prepares both by producing
stable evidence fields and shortlist triggers.

## Chosen Approach

Add a small `public_data` layer that reads local ODRE and ECO2MIX exports into normalized,
tested records. Portfolio scoring consumes only normalized evidence objects, not raw CSV or
TSV rows. This keeps source parsing, product scoring, and client reporting separate.

RTE7000 remains in the workflow as optional topology identity evidence. It is valuable for
canonical substation linking and Class A confidence gates, but it must not become the only
source of commercial truth. ODRE, Cartostock, OSM, and client facts remain visible in the
evidence register.

## Source Roles

### ODRE

ODRE local files provide public and reconstructed context:

- `postes-electriques-rte.csv`: RTE substation code, name, state, voltage, department.
- `contraintes-region.csv`: regional constraints, affected works, linked substations,
  occurrence, duration, persistence, and day-specificity.
- `energies-et-puissances-regionales-liees-au-contraintes.csv`: regional constrained
  renewable energy and power signals.
- `registre-national-installation-production-stockage-electricite-agrege.csv`: generation
  and storage assets by region, source substation, technology, connection voltage, power,
  and stockable energy.
- `soutirages-regionaux-quotidiens-*.csv`: regional half-hourly load context by sector
  and voltage.

These data can support regional risk and opportunity signals. They must not be described as
nodal measurements or official available capacity.

### ECO2MIX

ECO2MIX files downloaded with `.xls` extensions are tab-separated text exports. They provide
national operating context: consumption, production by technology, exchanges, CO2 signal,
battery storage fields when available, and Tempo calendar data.

For this tranche, ECO2MIX is a system-context signal only. It may support interpretation of
stress periods and economic narratives, but not site-level electrical feasibility.

### RTE7000

RTE7000 is used when available to strengthen canonical substation identity and topology
evidence. It remains revision-pinned and remotely projected. A missing RTE7000 source should
degrade confidence, not erase all ODRE/Cartostock/OSM evidence.

## Components

### Public Data Loaders

Create a `thesegrid.public_data` package with source-specific modules:

- `odre.py`: read and normalize local ODRE CSV exports with UTF-8 BOM handling.
- `eco2mix.py`: read RTE TSV exports even when filenames end in `.xls`.
- `evidence.py`: combine normalized public data into portfolio-facing evidence profiles.

Each loader validates required columns, records source path, file size, SHA-256 hash, row
count, and transformation version.

### Public Grid Evidence Profile

Each site/candidate pair receives a `PublicGridEvidenceProfile` with fields suitable for
scoring and reporting:

- regional constraint count;
- dominant constraint occurrence;
- dominant constraint duration;
- high-persistence constraint count;
- constrained renewable-energy indicator;
- storage/BESS density by region;
- storage/BESS density by matched source substation when available;
- regional load data availability and latest date;
- ECO2MIX system-context coverage;
- source completeness score;
- missing evidence labels.

The profile is descriptive. It does not output a probability of connection success.

### Portfolio Ranking Integration

The existing `portfolio_screening.py` score remains transparent and class-based. This
tranche adds public-evidence dimensions without changing the commercial classes:

- `A / prioritize`;
- `B / investigate`;
- `C / hold`;
- `D / reject`.

Class A still requires deterministic identity and RTE7000 topology link when RTE7000 is
available. Strong ODRE/ECO2MIX signals can improve ranking within a class, but cannot
override weak substation identity.

### Deep Dive Trigger

The ranking output adds a `deep_dive_recommendation` field:

- `recommended`: strong candidate and enough evidence to scope a Deep Dive;
- `conditional`: promising but requires manual identity/source review first;
- `not_recommended`: weak, rejected, or insufficient fit.

The trigger is a shortlist mechanism only. It does not run QSTS, XIIDM, or PyPowSyBl.

### Site Finder Preparation

The normalized public-evidence layer can later be reused by Site Finder. This tranche does
not generate prospecting zones. It only ensures regional and substation evidence can be
computed independently from a client portfolio.

## Outputs

Portfolio Screening V2 should continue writing the existing deliverables and add:

- public evidence columns to `portfolio_ranked.csv`;
- public evidence columns to `candidate_substations.csv` where candidate-specific;
- `public_grid_evidence.csv` with one row per site/candidate evidence record;
- source metadata for local ODRE/ECO2MIX files in `run_manifest.json`;
- a report section explaining ODRE/ECO2MIX signals and their limits;
- a recommended Deep Dive shortlist section.

## Failure Handling

Missing ODRE or ECO2MIX files should not block geospatial screening. The affected evidence
fields become empty, the source is recorded as unavailable, and the evidence score is reduced.

Schema drift in a provided local file raises a source-specific error with the filename and
missing columns. A malformed ECO2MIX `.xls` text export raises a clear parse error explaining
that the expected format is tab-separated text.

## Testing

Unit tests should use small in-memory or temporary-file fixtures. They must cover:

- ODRE column validation and UTF-8 BOM handling;
- ECO2MIX TSV parsing despite `.xls` extension;
- source manifests and hashing;
- regional constraint aggregation;
- BESS/storage aggregation by region and source substation;
- evidence profile construction with partial sources;
- ranking changes that remain deterministic;
- report and CSV serialization.

## Scientific Boundary

This tranche improves commercial triage and evidence quality. It does not create official
capacity, official queue, PTF, bay availability, N-1, protection, short-circuit, stability,
or cost conclusions.

The commercial claim remains: VoltPath helps a BESS developer decide which sites deserve
priority and which ones justify a deeper study.
