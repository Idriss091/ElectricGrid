# Data and modeling stack

## Purpose

This document defines the initial data sources, simulation tools, and modeling assumptions for the research prototype and future product.

The goal is to build a robust first prototype without depending immediately on private grid-operator data.

## Initial stack

### SimBench

SimBench provides benchmark electrical networks with annual profiles for:

- load;
- generation;
- storage.

Use SimBench for reproducible experiments and scientific validation.

### pandapower

pandapower is the main Python tool for:

- power flow;
- optimal power flow;
- hosting capacity analysis;
- time-series simulation;
- network constraint checks.

pandapower should be the first implementation layer for the MVP because it integrates well with Python, testing, notebooks, and reproducible experiments.

### OpenDSS

OpenDSS is useful for more detailed distribution-network simulations, especially:

- QSTS simulations;
- seasonal ratings;
- voltage behavior;
- time-dependent network constraints.

OpenDSS is not required for the very first MVP, but it may become important for validation.

## QSTS assumptions

QSTS runs are buyer-side pre-feasibility studies, not official grid-operator studies.

The current implementation uses hourly profile steps. Annual half-hourly and quarter-hourly
profiles are aggregated to hourly values before simulation. Full-year SimBench profile years
with 8,760 or 8,784 hourly steps are preserved as-is.

QSTS requests carry an explicit `profile_year`, currently defaulting to 2026 for backward
compatibility. The year is used only to map hourly profile indices to calendar timestamps
and to compute stratified monthly weights, including leap-year February weights.

For stratified QSTS, each sampled timestamp represents a weighted block of annual hours.
Expected curtailed energy and tail curtailment quantiles must use those timestamp weights.
Unweighted sampled metrics are retained only as diagnostic evidence.

A candidate connection must not be certified as incrementally feasible for a timestamp when
the baseline power flow for that timestamp does not converge. Such timestamps are treated as
unusable evidence until the baseline model or solver assumptions are corrected.

## French public data

RTE public data can be used to enrich assumptions about:

- consumption;
- production;
- system context;
- available connection capacity where public maps exist.
