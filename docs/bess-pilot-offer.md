# BESS flexible connection pre-screen

## Offer

Thesegrid provides a buyer-side pre-feasibility report for BESS grid-connection
decisions.

The service helps answer:

- which candidate site or bus should be prioritized;
- what firm MW appears technically feasible;
- what conditional MW may be feasible under a flexible envelope;
- what curtailment risk appears in MW and MWh;
- whether the requested MW should be accepted, rejected, or resized;
- what assumptions should be taken into a formal consultant or operator study.

## What this is not

This is not an official RTE, Enedis, or network-operator connection study.

It does not replace short-circuit, protection, dynamic stability, N-1, harmonic, or
operator planning studies.

It is an upstream decision aid for developers, consultants, and investors.

## Pilot inputs

Preferred inputs:

- candidate sites or buses;
- requested MW values;
- BESS operating assumptions;
- curtailment tolerance in MW and MWh;
- network model or export;
- hourly or sub-hourly load/generation profiles when available;
- voltage and thermal limits;
- economic proxy assumptions.

If no client network model is available, the first discussion should focus on whether a
consultant, anonymized model, or public reconstruction is feasible.

## Pilot outputs

The pilot produces:

- site or bus ranking;
- firm injection and withdrawal MW;
- conditional capacity estimate;
- dominant constraints;
- QSTS curtailment metrics when time-series data is available;
- P50/P90/P95/P99 curtailment diagnostics;
- recommended flexible envelope;
- go / go-with-conditions / no-go / resize-recommended verdict;
- proxy economics;
- HTML/PDF-style investor report;
- CSV/JSON outputs for auditability;
- assumptions and limitations.

## Suggested pilot packages

### Single-site pilot

Indicative price: EUR 5k-8k when a clean model is provided.

Use case: one candidate project, a small number of requested MW values, and a concise
decision memo.

### Portfolio pre-screen

Indicative price: EUR 12k-25k for 3-5 candidate sites or buses.

Use case: rank a shortlist, identify false positives, and decide which sites deserve
deeper study.

### Larger pipeline screen

Indicative price: EUR 30k+ depending on model quality, number of sites, and QSTS scope.

Use case: screen a development pipeline before spending more capital on formal studies.

## Discovery questions

Use these questions in the first call:

- How many BESS sites are you currently screening?
- At what stage do you usually discover that a point of connection is not viable?
- Do you test several MW sizes before submitting or advancing a project?
- Have you considered flexible connection offers or injection/soutirage gabarits?
- Who performs your first grid studies today?
- What data could you share for an anonymized pilot?
- What would make a pre-screening report useful for an investment committee?
- What false-positive or late-stage rejection would this help avoid?

## Short outreach message

```text
Bonjour [Prénom],

Je développe Thesegrid, un moteur de pré-faisabilité pour raccordements flexibles BESS.

L'objectif est de classer rapidement des sites candidats, estimer la puissance
ferme/conditionnelle, identifier les contraintes réseau probables, quantifier le
curtailment et recommander une puissance ou une enveloppe flexible avant étude
officielle.

Je cherche 3 pilotes payants avec des développeurs ou bureaux d'études BESS,
idéalement sur un portefeuille de sites ou un cas anonymisé.

Est-ce que le sujet raccordement flexible / gabarit / puissance optimale est actif
chez vous en ce moment ?
```
