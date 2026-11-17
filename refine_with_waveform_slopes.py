"""Test a slope-informed rate estimate with a bounded downward correction."""
import json
import zipfile

import numpy as np
from scipy.signal import butter, sosfiltfilt

from adaptive_peaks import counts, outcome
from audit_refined_rates import load_development_rates
from baseline import OUT, ROOT, read_wave, write_table
from compare_quality import TOLERANCE
from refine_displayed_rate import AGREEMENT_BPM, group_predictions, lag_agreement, rate_features, spectral_support


def slope_features(waves, fs):
    pulse = sosfiltfilt(butter(3, [0.68, 4.7], fs=fs, btype="bandpass", output="sos"), waves, axis=0)
    normalized = pulse / np.maximum(np.percentile(abs(pulse), 85, axis=0), 1e-9)
    slope = np.gradient(np.clip(normalized, -2, 2), axis=0)
    traces = ([normalized[:, 1] - normalized[:, 0], normalized[:, 2] - normalized[:, 0]]
              if waves.shape[1] == 3 else normalized.T)
    features = [
        *spectral_support(slope, fs, (1, 2)),
        lag_agreement(slope, fs, 1),
        *spectral_support(normalized, fs, (1,)),
        *spectral_support(np.stack(traces, axis=1), fs, (1, 2)),
    ]
    return np.column_stack([stat for values in features for stat in (values.mean(axis=1), values.max(axis=1))])


def select_rate(peak, periodic, peak_score, periodic_score, slope_rate, slope_score):
    if abs(periodic - peak) <= AGREEMENT_BPM:
        guarded = (peak * peak_score + periodic * periodic_score) / (peak_score + periodic_score)
    elif periodic_score > peak_score:
        guarded = max(periodic, peak - TOLERANCE)
    else:
        guarded = peak
    use_slope = slope_score > max(peak_score, periodic_score)
    return ((guarded + slope_rate) / 2 if use_slope else guarded), use_slope


def main():
    source, _ = load_development_rates()
    features = []
    with zipfile.ZipFile(ROOT / "data/butppg-2.0.0.zip") as archive:
        prefix = next(name.rsplit("/", 1)[0] + "/" for name in archive.namelist()
                      if name.endswith("/subject-info.csv"))
        for row in source:
            waves, fs = read_wave(archive, prefix, row["id"], "PPG", all_ppg_channels=True)
            features.append(np.column_stack([rate_features(waves, fs), slope_features(waves, fs)]))
    qrs = np.array([float(r["qrs_bpm"]) for r in source])
    people = np.array([r["person"] for r in source])
    rates, scores, folds = group_predictions(np.array(features), qrs, people, max_iter=65)
    rows = []
    for row, ref, rate, score, fold in zip(source, qrs, rates, scores, folds):
        current = float(row["refined_bpm"])
        retry = row["refined_outcome"].startswith("retry_")
        if retry:
            revised, use_slope = current, False
        else:
            revised, use_slope = select_rate(float(row["prior_bpm"]), float(row["periodic_bpm"]),
                                             float(row["prior_score"]), float(row["periodic_score"]), rate, score)
        rows.append(dict(id=row["id"], person=row["person"], fold=int(fold), qrs_bpm=float(ref),
                         peak_bpm=float(row["prior_bpm"]), previous_bpm=current, slope_bpm=float(rate),
                         slope_score=float(score), used_slope=bool(use_slope), revised_bpm=float(revised),
                         peak_outcome=row["prior_outcome"],
                         previous_outcome=row["refined_outcome"], revised_outcome=outcome(revised, ref, retry)))
    write_table("slope-refinement.csv", rows)
    write_summary(rows)


def write_summary(rows):
    old = counts([r["previous_outcome"] for r in rows])
    new = counts([r["revised_outcome"] for r in rows])
    fixed = [r for r in rows if r["previous_outcome"] == "show_bad" and r["revised_outcome"] == "show_good"]
    new_errors = [r for r in rows if r["previous_outcome"] == "show_good" and r["revised_outcome"] == "show_bad"]
    nine = [r for r in rows if r["peak_outcome"] == "show_good" and r["previous_outcome"] == "show_bad"]
    recovered = [r for r in nine if r["revised_outcome"] == "show_good"]
    assert len(nine) == 9 and old["show_bad"] == 375
    assert (old["retry_good"], old["retry_bad"]) == (new["retry_good"], new["retry_bad"])
    report = dict(attempts=len(rows), people=len({r["person"] for r in rows}), previous=old, revised=new,
                  displayed_errors_fixed=len(fixed), new_displayed_errors=len(new_errors),
                  recovered_from_nine=recovered, original_nine=nine,
                  previously_good_peak_now_wrong=sum(r["peak_outcome"] == "show_good" and
                                                      r["revised_outcome"] == "show_bad" for r in rows),
                  per_100={label: {key: value * 100 / len(rows) for key, value in totals.items()}
                           for label, totals in [("previous", old), ("revised", new)]})
    text = json.dumps(report, indent=2)
    (OUT / "slope-refinement-summary.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
