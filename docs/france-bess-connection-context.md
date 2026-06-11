# France BESS connection context

VoltPath V1 is scoped to buyer-side pre-feasibility for BESS in France. It helps a
developer or advisor decide whether a site deserves further grid-connection work before
an official operator study.

## Public context

RTE announced storage connection offers with gabarits after a CRE consultation. The
updated RTE technical reference material for storage gabarits and PTF templates entered
into force on 2026-02-12. VoltPath uses this as market context and vocabulary, not as a
source of official project-specific limits.

CRE TURPE 7 introduced an optional annual injection-withdrawal component for storage
capacity connected at HTA, HTB1, and HTB2 from 2026-08-01. CRE also published eligible
injection and withdrawal zones in 2025. Those zones support the product language of
`zone contrainte`, `injection`, `soutirage`, and `capacite d'accueil`.

RTE public storage capacity tools such as Cartostock and Capareseau are useful for
market interpretation. They do not provide a full cost, delay, physical feasibility, or
official connection offer for a specific project.

## Product vocabulary

- `PTF`: proposition technique et financiere. VoltPath output is not a PTF.
- `gabarit injection/soutirage`: direction-specific operating envelope used as a
  pre-feasibility proxy.
- `capacite d'accueil`: public-context available hosting capacity signal, not a
  guaranteed connection capacity.
- `zone contrainte`: area where network constraints may justify a gabarit-style
  connection offer.
- `offre optimisee`: RTE/CRE market context for storage gabarits; VoltPath only
  produces an investor-side approximation.

## Boundaries

The V1 gabarit preset is named `rte_cre_inspired_v1` to avoid implying official status.
It is a conservative pre-feasibility proxy. It does not replace RTE, Enedis, or official
operator studies and excludes short-circuit, protection, stability, N-1 security,
harmonics, land, physical bay availability, cost, and delay checks.

## Sources to track

- RTE Services Portal, storage gabarit connection offers, published 2026-02-20.
- CRE, TURPE 7 injection-withdrawal eligible zones, published 2025-10-09.
- CRE deliberation 2026-32 on RTE storage gabarit connection procedure.
- RTE public storage capacity pages, including Cartostock and Capareseau context.
