# French Substation Identity Design

## Objective

Build the first conservative cross-source identity layer for French substations.

The layer links:

- local Cartostock rows to ODRE substations using deterministic name and voltage rules;
- ODRE substations to RTE7000 substations using exact technical codes.

It deliberately does not use global fuzzy matching, geographic inference, OpenStreetMap,
or manual overrides in this tranche.

## Inputs

### Cartostock

The loader reads the semicolon-delimited local export and validates the twelve expected
columns. Each row is normalized into a `CartostockSubstation` containing:

- Cartostock identifier;
- raw address label;
- extracted station name;
- normalized station name;
- voltage in kV;
- INSEE commune code and commune name;
- public Cartostock signals.

### ODRE

The ODRE loader reads the public `postes-electriques-rte` CSV export through an
injectable byte fetcher. It records the source URL, retrieval timestamp, row count, and
`public_signal` source type.

Each row is normalized into an `OdreSubstation` containing its technical code, station
name, normalized name, voltage, function, status, and department.

### RTE7000

The caller supplies a RTE7000 substation frame from the existing remote-data module.
The identity layer requires an `id` column and links it to ODRE by exact code only.

## Matching Policy

Cartostock to ODRE:

- `exact`: one ODRE candidate has the same normalized name and voltage;
- `high`: no exact-voltage candidate exists, but the normalized name resolves to one
  unique ODRE technical code;
- `unmatched`: no deterministic candidate or more than one unresolved candidate.

RTE7000 enrichment:

- retain all Cartostock-to-ODRE matches;
- set `rte7000_id` only when the matched ODRE technical code occurs exactly in the
  supplied RTE7000 frame;
- keep the original Cartostock confidence because RTE7000 linking is exact-code
  evidence, not a new heuristic.

Every match records its method and candidate count. Ambiguous results do not silently
select a candidate.

## Outputs

`FrenchSubstationIdentity` exposes:

- Cartostock identity and public context;
- matched ODRE code and normalized name when available;
- exact RTE7000 identifier when available;
- match confidence: `exact`, `high`, or `unmatched`;
- match method;
- candidate count;
- manual-review flag.

`unmatched` rows and all ambiguous rows require manual review.

## Validation

Tests use small in-memory fixtures and injected readers/fetchers. They cover schema
validation, French text normalization, voltage extraction, exact/high/ambiguous matching,
exact RTE7000 enrichment, deterministic ordering, and provenance serialization.

