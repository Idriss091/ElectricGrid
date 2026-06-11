# RTE7000 Remote Data Access Design

## Objective

Provide a small, testable foundation for reading selected `OpenSynth/rte7000` Parquet
partitions directly from Hugging Face without cloning or downloading the complete
dataset.

This is the first implementation tranche of
`docs/v2-commercial-product-objectives.md`. It does not implement substation matching,
portfolio scoring, ODRE ingestion, D-GITT XIIDM loading, or PyPowSyBl calculations.

## Public Interface

The new `thesegrid.rte7000_data` module exposes:

- `Rte7000PartitionRequest`: repository, immutable revision, component, year, month,
  selected columns, and optional Parquet row filters;
- `Rte7000PartitionResult`: the resulting pandas frame and its provenance manifest;
- `Rte7000PartitionManifest`: repository, revision, remote path, selected columns,
  filters, row count, and retrieval timestamp;
- `read_rte7000_partition`: validate the request, read one remote Parquet partition,
  validate the returned schema, apply equality filters, and return data plus provenance.

Supported components in this tranche are the current RTE7000 directories:
`branch`, `bus`, `gen`, `load`, `sub`, `switch`, and `vol`.

## Remote Access

Remote paths use the immutable Hugging Face form:

`hf://datasets/<repository>@<revision>/<component>/<component>_<year>-<month>.parquet`

The revision is mandatory and must not be `main`. Normal use reads only the requested
partition and columns. The Parquet engine may use a bounded local HTTP/cache layer
internally, but the API never requests a complete dataset snapshot.

The implementation uses `pandas.read_parquet` with the `pyarrow` engine, projected
columns, predicate pushdown, and an injectable reader callable. Filter columns do not
need to be returned in the selected columns. Reader injection keeps unit tests offline
and permits future migration to a different Parquet query engine without changing the
product interface.

## Validation and Failure Modes

Requests reject:

- unsupported components;
- mutable or empty revisions;
- years outside 2021-2023, matching the current published dataset;
- invalid months;
- empty or duplicate selected columns;
- empty filter-column names.

The reader wraps remote-access failures in `Rte7000DataAccessError`. Missing requested
columns raise `Rte7000SchemaError`. Filters use exact equality and preserve deterministic
row order.

## Verification

Unit tests cover path construction, revision pinning, column projection, filtering,
schema drift, invalid requests, and wrapped remote failures. An opt-in live test may
read a small column projection from Hugging Face, but the normal test suite remains
network-independent.
