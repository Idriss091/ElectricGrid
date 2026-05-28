# Client network input format

## Purpose

This document defines the target input package for applying Thesegrid to a client,
consultant, or operator-grade network model instead of a SimBench benchmark network.

The current investor bundle uses SimBench to prove the workflow. A commercial pilot
should use either a client-supplied model or a clearly documented reconstructed model.

## Input package

Preferred folder shape:

```text
client_network/
  metadata.yaml
  buses.csv
  lines.csv
  transformers.csv
  loads.csv
  generators.csv
  storage.csv
  profiles_load.csv
  profiles_generation.csv
  profiles_storage.csv
  constraints.yaml
```

For a first pilot, not every file is mandatory. The minimum static screening package is:

- `metadata.yaml`
- `buses.csv`
- `lines.csv`
- `transformers.csv` when transformers are present
- `loads.csv`
- `constraints.yaml`

The minimum QSTS package also needs hourly or sub-hourly profiles for load and relevant
generation.

## Required metadata

`metadata.yaml` should include:

```yaml
schema_version: thesegrid-client-network-v1
data_source_type: client_model # benchmark | client_model | public_reconstruction | operator_validated
network_name: example_network
country: FR
voltage_level: MV
created_by: client_or_consultant_name
created_at: 2026-05-22
notes: "Pre-feasibility model; not an official connection study unless stated."
```

`data_source_type` is important because the report must distinguish benchmark evidence
from client or operator-grade evidence.

## Core tables

### buses.csv

Required columns:

- `bus_id`
- `name`
- `vn_kv`
- `in_service`

Optional columns:

- `zone`
- `substation`
- `latitude`
- `longitude`

### lines.csv

Required columns:

- `line_id`
- `from_bus`
- `to_bus`
- `length_km`
- `r_ohm_per_km`
- `x_ohm_per_km`
- `c_nf_per_km`
- `max_i_ka`
- `in_service`

Optional columns:

- `name`
- `type`
- `max_loading_percent`

### transformers.csv

Required columns when transformers are present:

- `trafo_id`
- `hv_bus`
- `lv_bus`
- `sn_mva`
- `vn_hv_kv`
- `vn_lv_kv`
- `vk_percent`
- `vkr_percent`
- `pfe_kw`
- `i0_percent`
- `in_service`

### loads.csv

Required columns:

- `load_id`
- `bus_id`
- `p_mw`
- `q_mvar`
- `in_service`

### generators.csv

Use this for generators or static generation already connected to the network.

Required columns:

- `generator_id`
- `bus_id`
- `type`
- `p_mw`
- `q_mvar`
- `in_service`

## Profiles

Profiles should be indexed by timestamp and use element ids as columns.

Example:

```csv
timestamp,load_1,load_2,load_3
2026-01-01T00:00:00,1.2,0.4,0.8
2026-01-01T01:00:00,1.1,0.5,0.9
```

Accepted time resolution for pilots:

- hourly preferred;
- 15-minute acceptable if it can be aggregated or replayed consistently.

Every report must state the profile period and whether profiles are measured, simulated,
or proxy assumptions.

## Constraint settings

`constraints.yaml` should include:

```yaml
voltage_min_pu: 0.95
voltage_max_pu: 1.05
max_loading_percent: 100.0
candidate_asset: bess
candidate_power_factor: 1.0
```

The MVP does not cover short-circuit, protection, dynamic stability, N-1 security, or
harmonics. If those studies are needed, they must be listed as follow-up official or
consultant studies.

## Pilot acceptance levels

Thesegrid reports should label evidence as:

- `benchmark_demo`: SimBench or other public benchmark evidence;
- `client_model_static`: client model with static screening only;
- `client_model_qsts_sampled`: client model with sampled or stratified QSTS;
- `client_model_qsts_full_year`: client model with full-year QSTS;
- `operator_validated`: only when the input model and assumptions are validated by an
  operator or official study process.

## First commercial pilot

For the first paid pilot, a client can provide either:

1. a pandapower network file plus profiles;
2. CSV tables following this document;
3. an anonymized network export that can be converted into pandapower;
4. a consultant-prepared model with explicit assumptions.

The output remains buyer-side pre-feasibility and does not replace the official
connection study.

## Validation command

Before using a client package in a pipeline, validate the folder structure and declared
schema:

```bash
thesegrid validate-client-network \
  --client-network client_network/ \
  --output results/client_network_validation
```

The command writes:

- `client_network_validation.json`
- `client_network_validation.md`

This validation checks required files, required CSV columns, flat `metadata.yaml`, and
flat `constraints.yaml`. It does not certify electrical correctness and does not convert
the package into a pandapower network yet.
