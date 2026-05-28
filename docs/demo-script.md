# Investor Demo Script

This is the historical manual demo script. For the current reproducible demo, start
with `docs/demo-pipeline.md` and generate a fresh local bundle under `results/`.

Use this file only as narrative support for a 10-minute walkthrough of the BESS
flexible-connection thesis.

## Demo Setup

- Network: `1-MV-rural--0-sw`
- Asset: BESS
- Requested capacity: 5 MW
- Representative buses: 2, 21, and 24
- QSTS P90 curtailment tolerance: 3 MW
- QSTS expected curtailed-energy tolerance: 60 MWh
- Constraint settings: 0.95-1.05 pu voltage band and 100% thermal loading limit
- France context: RTE/CRE-inspired storage gabarit vocabulary, not an official PTF

The demo is a buyer-side pre-feasibility workflow. It does not replace an official
grid-connection study.

## 10-Minute Flow

### 1. Market Problem

Developers need to know whether a BESS site is worth pursuing before waiting for a full
operator study. The relevant decision is not only hosting capacity. It is whether firm
capacity, conditional capacity, curtailment risk, and economic value support a go,
no-go, or go-with-conditions recommendation.

### 2. Static Screening

Open the generated pipeline outputs:

- `results/demo_pipeline_stratified_smoke/screening/screening_summary.md`
- `results/demo_pipeline_stratified_smoke/screening/screening.csv`

Explain that static screening ranks active MV candidate buses using steady-state
pandapower checks. It is a fast proxy layer for site prioritization.

Current command:

```bash
thesegrid run-pipeline \
  --network 1-MV-rural--0-sw \
  --requested-mw 5 \
  --max-buses 3 \
  --stratified-max-candidates 1 \
  --run-qsts-stratified \
  --output results/demo_pipeline_stratified_smoke
```

### 3. QSTS Validation

Open:

- `results/demo_pipeline_stratified_smoke/qsts_stratified/qsts_summary.md`
- `results/demo_pipeline_stratified_smoke/qsts_stratified/investment_memo.md`
- `results/demo_pipeline_stratified_smoke/pipeline_report.md`

Explain that QSTS is the higher-evidence layer because it replays time-varying network
operating points and compares candidate-caused violations against a no-candidate
baseline.

For full-year evidence, use the long-running command in `docs/demo-pipeline.md`.
Full-year QSTS should be treated as a job, not as a quick interactive smoke check.

Historical lower-level full-year command shape:

```bash
thesegrid qsts \
  --network 1-MV-rural--0-sw \
  --screening-csv <screening.csv> \
  --requested-mw 5 \
  --bus-ids 2 \
  --p90-curtailment-tolerance-mw 3 \
  --expected-curtailment-tolerance-mwh 60 \
  --output results/<full_year_job> \
  --progress-every-n-hours 2000
```

### 4. Investor Decision

Use the QSTS investor decision table:

| bus | verdict | interpretation |
| ---: | --- | --- |
| 2 | `go` in stratified, `no-go` full-year | The stratified sample misses rare annual energy risk. |
| 21 | `no-go` | P90 is below 3 MW, but expected curtailed energy exceeds 60 MWh. |
| 24 | `no-go` | P90 is below 3 MW, but expected curtailed energy exceeds 60 MWh. |

The key message is that P90 alone is not enough, and sampling alone is not enough for a
bankable-looking conclusion. In the full-year bus 2 run, QSTS P90 remains 0 MW while
expected curtailed energy reaches 120.977 MWh, which flips the verdict to `no-go`.

### 5. Flexible Envelope

Open:

- `contractual_envelope.csv`
- `static_vs_qsts_comparison.csv`
- `docs/france-bess-connection-context.md`

Explain that the contractual envelope compresses QSTS-derived hourly allowed MW into
direction, season, and time-block rows. The P10 allowed MW is the conservative contract
value. P25, P50, and minimum allowed MW are diagnostic fields.

Use French product language deliberately: PTF, gabarit injection/soutirage, capacite
d'accueil, zone contrainte, and offre optimisee. State that Thesegrid does not produce a
PTF or official offer.

### 6. Calibration Sweep

For the MVP investor calibration campaign, use a dedicated generated output directory:

```bash
thesegrid qsts-sweep \
  --config experiments/investor_mvp_calibration.json \
  --output results/investor_mvp_2026-05-18/qsts_calibration
```

This sweep intentionally includes both stratified and full-year sampling. Full-year runs
can be slow; keep them as explicit calibration jobs rather than synchronous UI requests.

### 7. Resize Recommendation

When a requested MW is rejected, use `qsts-resize` to find the largest lower MW that
meets the selected decision-frontier policy:

```bash
thesegrid qsts-resize \
  --network 1-MV-rural--0-sw \
  --screening-csv <screening.csv> \
  --bus-id 24 \
  --requested-mw 5 \
  --min-mw 2 \
  --step-mw 1 \
  --p90-curtailment-tolerance-mw 3 \
  --expected-curtailment-tolerance-mwh 60 \
  --selected-policy standard \
  --output results/<resize_job>
```

### 8. Close

End with three boundaries:

- The workflow is useful for early site selection and investment triage.
- SimBench and public context are not substitutes for confidential operator models.
- Sampling is useful for fast triage, but full-year QSTS is needed before presenting a
  robust investment conclusion.
