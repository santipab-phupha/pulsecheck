# PulseCheck evaluation

## Protocol

- **Dataset** — BUT PPG v2.0.0, restricted to fingertip smartphone PPG segments. The retained windows last 10 seconds and each has a simultaneous ECG with QRS annotations.
- **Split** — 1,540 attempts from 24 people in development and 386 attempts from 6 other people in the final test. The participant-level split used seed 42 and is recorded in the [manifest](results/fingertip-manifest.csv).
- **Comparator** — The previous model uses PPG waveform slope to refine the candidate rate. The latest adds a spectral support check. Both use a single quality gate fixed at the 23rd percentile of out-of-fold peak scores across four development folds grouped by participant. The [lock](results/final-holdout-lock.json) records the exact cutoff, model settings, runtime, and SHA-256 hashes.
- **Reference** — For each window, the reference is the median of the instantaneous bpm values derived from consecutive annotated ECG QRS intervals. A development audit compared these rates with the dataset's HR CSV and independently checked discordant windows against the ECG waveform. See the [reference audit](results/reference-audit-summary.json).
- **Scoring** — An estimate within ±5 bpm of ECG counts as within tolerance. A repeat request is classed as unnecessary if its internal estimate falls within that tolerance. Rates are pooled across all 386 attempts, so participants with more recordings contribute more weight. The 5 bpm threshold is an experiment scoring rule.

The models and thresholds were locked before the six-person test. The [PPG-only predictions](results/final-holdout-predictions.csv) were saved before attaching ECG references to the [paired comparison](results/final-holdout-comparison.csv).

## Held-out results

| Outcome | Previous count | Previous per 100 | Latest count | Latest per 100 |
| --- | ---: | ---: | ---: | ---: |
| Displayed outside tolerance | 110 | 28.50 | 109 | 28.24 |
| Displayed within tolerance | 216 | 55.96 | 217 | 56.22 |
| Repeat requested outside tolerance | 40 | 10.36 | 40 | 10.36 |
| Repeat requested within tolerance | 20 | 5.18 | 20 | 5.18 |
| All repeats | 60 | 15.54 | 60 | 15.54 |

All 386 attempts produced an internal estimate. The latest model brought one of the 110 previously incorrect displayed readings within tolerance. It displayed 326 estimates and missed tolerance on 109 of them (33.4%). The [full report](results/final-holdout-summary.json) includes counts by participant and paired outcome transitions.

## Limits

The 386 windows came from six people, with multiple windows per person, so these results provide limited evidence about performance on new phones or populations. The observed improvement is one window and is descriptive. Repeat requests were simulated decisions on previously recorded signals. A prospective study would be needed to learn how often a real repeat improves the result.

The two replay examples illustrate development outcomes. **135021** improves from 74.0 to 67.6 bpm against 65.0 bpm on ECG. **136096** stays at 72.7 bpm against 63.4 bpm. These values are rounded for the demo. The live browser camera path uses a separate experimental estimator and lacks ECG validation.

An incorrect value could cause someone to overlook an abnormal reading or seek unnecessary care. The current result supports continued research on signal quality warnings and repeat prompts. For replication steps, see the [README](README.md).
