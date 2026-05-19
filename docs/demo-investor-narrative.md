# Investor Demo Narrative

## 1. Market Problem

BESS developers need to decide whether a site is worth pursuing before waiting for a
full official grid-connection study. The useful early decision is not only hosting
capacity; it is whether firm capacity, conditional capacity, curtailment risk, and
proxy economics justify continuing, resizing, or abandoning the site.

## 2. Demo Scenario

- Network: `1-MV-rural--0-sw`
- Asset: BESS
- Requested capacity: 5 MW
- Candidate buses: 2, 21, 24
- QSTS P90 curtailment tolerance: 3 MW
- Expected curtailed-energy tolerance: 60 MWh
- Full-year reference: 8784 hourly QSTS steps

## 3. Evidence Layers

Static screening ranks candidate buses quickly. Short QSTS is a smoke validation layer.
Stratified QSTS gives pre-demo annual evidence. Full-year QSTS is the MVP investor
reference layer, while still not replacing an official operator study.

## 4. Current Result

Bus 2 looks acceptable in screening and stratified QSTS, but full-year QSTS changes the
decision to `no-go`: P90 curtailment remains 0 MW, while expected curtailed energy
reaches 120.976562 MWh and exceeds the 60 MWh tolerance.

Bus 21 is `no-go` in full-year QSTS. The expected curtailed energy is materially above
tolerance, so the site should be rejected or resized.

Bus 24 is also `no-go` at 5 MW. Full-year resize evidence shows 3 MW is still `no-go`,
while 2 MW becomes `go-with-conditions`.

## 5. Product Message

The demo should not be presented as “we replace RTE or Enedis studies.” The correct
message is:

> Thesegrid helps a BESS developer identify whether a site deserves more work, should be
> resized, or should be abandoned before spending time and capital on later-stage
> grid-connection work.

## 6. Resize Lesson

The most actionable output is not just `no-go`. It is:

> The requested 5 MW project is not acceptable at bus 24, but 2 MW is acceptable under
> the configured QSTS tolerances.

This turns network constraints into an investment decision.

## 7. Boundaries

The contractual envelope is an approximation pré-faisabilité inspired by RTE/CRE storage
gabarit vocabulary. It is not a PTF and not an official RTE/Enedis offer.

The workflow excludes short-circuit, protection, dynamic stability, N-1 security,
harmonics, land, physical bay availability, official cost, and official delay checks.

## 8. Bundle

Use `results/investor_bundle_2026-05-19/` as the current demo bundle. Start with:

- `investor_report.html`
- `scorecard.md`
- `README.md`
- `validation_matrix.md`
- `qsts_results.csv`
- `qsts_risk_summary.csv`
- `resize_results.csv`
- `contractual_envelope.csv`
- `run_manifest.json`

Use `next_calibration_campaign.md` to plan the next evidence expansion when more
compute time is available.
