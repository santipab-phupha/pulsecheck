# PulseCheck development notes

Reproduce from this directory with Python 3.11 and PowerShell.

```powershell
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Force data | Out-Null
curl.exe -fL --retry 3 -o data/butppg-2.0.0.zip https://physionet.org/content/butppg/get-zip/2.0.0/
python baseline.py
```

Archive SHA-256 `9b910fc884f63eca1c5d3a00c5710f838e0053dce94f8a02196bd0adc2ffa33c`.

## Method

Join the two metadata files by recording ID and select measurement site 1 (finger). Seed 42 selects 2 people from the original recording cohort and 4 from the extension for final testing. The full selection is saved in `results/fingertip-manifest.csv`. The current experiment uses the other 24 people only and includes every signal quality label.

Decode calibrated original single-channel PPG or inverted red intensity for the newer RGB files. Filter the 30 Hz signal at 0.6–4 Hz (third-order Butterworth, forward and backward). Detect peaks at least 0.30 s apart with prominence at least 35% of the filtered 95th-to-5th percentile range. Estimate heart rate as 60 divided by the median inter-peak interval in seconds when at least three peaks are present. Neither ECG nor reference annotations enter the estimator.

The reference is the study's ECG-derived median heart rate for each 10-second recording. The absolute difference of at most 5 bpm is the experiment's tolerance. Error summaries average estimated recordings, so people with more recordings carry more weight. All attempts, including missing estimates, are kept in `results/development-baseline.csv`. Empty estimate fields indicate insufficient peaks.

The two illustrations are the middle records by absolute error among resting examples within tolerance and finger-movement examples outside tolerance. Orange dots mark PPG peaks. ECG is high-pass filtered at 0.5 Hz for display only. Plot axes are independently scaled per case.

## Comparing estimators and quality checks

After the baseline run, execute `python compare_quality.py`. It reads the saved development rows and checks their IDs and peak estimates against the original experiment. Outputs are `results/quality-comparison.csv` (one row per attempt) and `results/quality-summary.json`.

The alternative estimator uses the strongest frequency between 36 and 200 bpm from a Hann-windowed periodogram of the detrended red PPG. Zero padding samples the spectrum more densely. The quality classifier predicts whether this estimate is within 5 bpm of the ECG reference. Its inputs are spectral concentration, disagreement between the two halves, disagreement with the peak estimate, log signal range, fraction of unchanged consecutive samples, and estimated bpm. ECG supplies training and evaluation labels only.

Each development participant is scored by a shallow random forest trained on the other 23. The cutoff is the training set's 30th percentile of out-of-bag scores, fixed before scoring the excluded person. A simple comparator rejects the bottom 30% by spectral concentration using a training-only cutoff. The actual retry fractions can differ on unseen people. Counts are per recording and retries are simulated requests. No follow-up measurement success is inferred.

The same cross-validation also evaluates a separately trained gate on the original peak estimator, using the same waveform features plus peak bpm. Only available peak estimates enter that gate. Attempts with no peak estimate are recorded separately and automatically request a repeat. Both gates target a 30% rejection rate among available estimates during training. For the paired comparison of estimator errors, use the 1,521 records with estimates from both methods.

## Auditing accepted errors and adjusting peak detection

After the quality comparison, run `python adaptive_peaks.py`. The script audits all 696 old accepted errors using recording conditions, author quality labels, and ECG beat counts from the original WFDB QRS annotations. A count difference describes the whole window; it does not identify specific missed beats.

The candidate uses the same red PPG, a 0.65–3.5 Hz bandpass, local amplitude normalization, local prominence, and sub-sample peak positions. It uses the same minimum peak spacing and median interval aggregation as the baseline. The quality forest is refitted on the new estimator's errors with the same 30% training rejection target and leave-one-person-out protocol. Rejection and unavailable estimates both count as a repeat request. The fixed-acceptance comparison also measures the new estimator on the exact windows originally displayed. This is an exploratory revision informed by development errors.

Per-record comparisons are in `results/adaptive-peaks.csv`; aggregate counts and the fate of the original accepted errors are in `results/adaptive-summary.json`.

## Selecting peaks across camera channels

Run these commands after generating the adaptive results.

```powershell
python reference_audit.py
python peak_selection.py
python peak_selection.py --training-reference qrs_bpm
```

The reference audit compares the published CSV against the median instantaneous rate of the ECG beats annotated in each matching 10-second segment. For discordant records, it independently detects peaks on the ECG waveform to check the timestamps. See `results/reference-audit-summary.json` and `results/reference-waveform-checks.csv`.

The peak selector constructs adaptive peak estimates for each available red, green, and blue trace and both polarities. A gradient-boosted tree model scores the candidates using peak spacing, spectral support, lag correlation, and agreement with other candidates. The best score determines the estimate and the repeat decision. In each outer fold, four inner folds grouped by person set a cutoff for the desired repeat rate using only training participants. Then the model refits on those participants and predicts the excluded participant. ECG helps define training and evaluation targets. Evaluation inputs come from PPG.

The scripts report repeat targets of 20%, 23%, 25%, and 30% on development data. The default 23% target is an exploratory operating point. `--retry-target` selects the point shown in the detailed comparison and the reference sensitivity checks. All rates use one attempt as the unit, and the 5 bpm tolerance is the experiment's scoring rule. Repeats describe the model's decisions on recorded signals.

The CSV-trained and QRS-trained runs write `results/peak-selection.csv` and `results/peak-selection-qrs.csv` with matching JSON summaries. In both summaries, the main comparison uses the official CSV for continuity, and `reference_sensitivity.qrs_all` compares both pipelines against the annotated ECG beat rate on all 1,540 windows. The 386 windows reserved for the final evaluation remain outside these experiments.

## Auditing and refining displayed QRS-trained rates

After generating `results/peak-selection-qrs.csv`, run these commands.

```powershell
python audit_displayed_errors.py
python refine_displayed_rate.py
```

The audit recomputes the selected peak train count and checks whether any candidate from the original detector was within 5 bpm of the same-window annotated ECG rate. Counts help identify under- and over-detection across the window. They do not establish a one-to-one beat match. See `results/displayed-error-audit.csv` and its JSON summary.

The refinement scores rates from 36 to 180 bpm in steps of 3 using spectral power, waveform correlation at the corresponding period, stability across the two halves, and agreement with peaks. It interpolates around the best-supported rate and compares the two PPG estimates on windows the prior gate accepted. When the two rates are within 3 bpm it averages them using their model scores as weights. Otherwise it takes the estimate with the higher score. These scores rank candidates and are not calibrated probabilities. This rule was chosen on the development set to limit changes to previously accurate estimates.

The periodicity model is trained in six person-grouped folds and the earlier peak model uses leave-one-person-out estimates. Both scores used for a row come from models that excluded that person's windows. The refinement preserves the prior retry decision and the internal estimate on all rejected windows. ECG supplies labels and the evaluation reference. The holdout remains outside the workflow. See `results/refined-rates.csv` and `results/refined-rates-summary.json`.

## Auditing the 375 remaining errors and testing waveform slopes

Run these commands after the first refinement and the 411-error audit.

```powershell
python audit_refined_rates.py
python refine_with_waveform_slopes.py
```

The first command audits all 375 incorrect displayed values and traces the nine regressions to the decision that produced each value. The second command adds spectral and lag evidence from the slope of the PPG waveform and from differences between color channels. It trains the same rate-grid classifier with 65 boosting iterations and six folds grouped by person.

On displayed windows where the earlier rule would replace the peak estimate with a lower periodic estimate, the decrease is capped at 5 bpm. The new slope-informed estimate is averaged with that guarded result only when its model score exceeds the prior two scores. This is an exploratory rule selected on the 24 development participants. The scores are rankings from different models. The original retry decision and internal estimate on retry windows are used for the before/after comparison. None of the final six participants are used.

The individual audit and comparison are in `results/refined-error-audit.csv` and `results/slope-refinement.csv`. Their JSON summaries report the nine regressions and the transitions from the previous version.

## Auditing the 367 remaining errors and checking spectral support

Run these commands after the waveform-slope refinement.

```powershell
python audit_slope_errors.py
python refine_with_spectral_checks.py
```

The audit identifies all 367 displayed errors, including the seven remaining regressions from the original peak estimate and the two introduced by the slope refinement. The new check measures the strongest per-channel fraction of PPG power within 0.105 Hz of each of the three proposed rates. A displayed slope adjustment is rolled back to the pre-slope rate if its support is less than half the strongest support for the peak and periodic estimates. The result is averaged with the original peak rate if the peak's spectral support leads both alternatives by more than 15% within 3 bpm or more than 50% within 10 bpm. The thresholds were explored on the 24 development participants. Both pipelines use the same QRS tolerance, attempt denominator, and retry decisions.

`results/spectral-refinement.csv` and its JSON summary record the primary comparison. `results/spectral-exploratory-comparison.csv` records a separate, higher-change exploratory run combining a stronger grouped rate model based on overlapping time windows with a cross-channel peak and spectral check. It fixed 57 of the 367 displayed errors, including all nine highlighted cases, and introduced 47 other displayed errors. The primary spectral check fixed four and introduced zero on the development set. Both analyses used only development recordings.
