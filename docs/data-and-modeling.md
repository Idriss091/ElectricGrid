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

## French public data

RTE public data can be used to enrich assumptions about:

- consumption;
- production;
- system context;
- available connection capacity where public maps exist.
