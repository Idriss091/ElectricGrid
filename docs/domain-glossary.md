# Domain glossary

## Firm capacity

Capacity available without special operational restriction.

## Conditional capacity

Additional capacity available if the project accepts predictable or controllable limitations.

## Flexible connection envelope

A time-dependent operating envelope defining when injection or withdrawal is allowed, limited, or forbidden.

## Curtailment

Energy or power reduction imposed because the network cannot accommodate the requested operation at a given time.

## EBITDA-at-risk

Economic downside caused by curtailment or operational constraints.

## Hosting capacity

Maximum amount of new generation, storage, or load that can be connected without violating network constraints.

## QSTS

Quasi-static time-series simulation used to validate network behavior over many time steps.

## Evidence level

Label describing how strong the current decision evidence is: `screening_only`,
`qsts_short`, `qsts_stratified`, or `qsts_full_year`.

## Validation matrix

Comparison table that aligns screening, short QSTS, stratified QSTS, and full-year QSTS
verdicts for the same candidate buses.

## BESS-lite

Minimal BESS sizing record used by the MVP pipeline: requested MW, duration, nominal
MWh, round-trip efficiency, and state-of-charge window. It is not a dispatch,
degradation, reserve-market, or bankable revenue model.

## Client network package

Structured `client_network/` folder containing metadata, network tables, profiles, and
constraints for a client, consultant, reconstructed public, or operator-validated model.
