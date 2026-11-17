"""Refine displayed rates with PPG periodicity on development participants."""
import json
import zipfile

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import butter, periodogram, sosfiltfilt
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from adaptive_peaks import counts, outcome
from audit_displayed_errors import development_rows
from baseline import ROOT, OUT, read_wave, write_table
from compare_quality import TOLERANCE
from peak_selection import peak_candidates

RATES = np.arange(36.0, 181.0, 3.0)
AGREEMENT_BPM = 3.0


def spectral_support(signal, fs, multipliers=(1, 2, 0.5), *, rates=RATES):
    frequencies, power = periodogram(signal, fs, window="hann", nfft=2048, axis=0)
    band_power = power[(frequencies > 0.48) & (frequencies < 4.7)].sum(axis=0).clip(1e-12)
    return [
        np.stack([power[np.abs(frequencies - rate * multiple / 60) <= 0.105].sum(axis=0) / band_power
                  for rate in rates])
        for multiple in multipliers
    ]


def lag_agreement(signal, fs, multiple):
    lags = np.clip(np.rint(multiple * 60 * fs / RATES).astype(int), 1, len(signal) // 2)
    result = []
    for lag in lags:
        first, second = signal[:-lag], signal[lag:]
        norm = np.maximum(np.linalg.norm(first, axis=0) * np.linalg.norm(second, axis=0), 1e-12)
        result.append((first * second).sum(axis=0) / norm)
    return np.stack(result)


def rate_features(waves, fs):
    rates = np.array([c[0] for c in peak_candidates(waves, fs)])
    distances = np.abs(RATES[:, None] - rates) if rates.size else np.full((len(RATES), 1), np.inf)
    pulse = sosfiltfilt(butter(3, [0.55, 4.7], fs=fs, btype="bandpass", output="sos"), waves, axis=0)
    envelope = median_filter(abs(pulse), size=(2 * fs + 1, 1), mode="nearest")
    floor = np.maximum(np.median(abs(pulse), axis=0) * 0.12, 1e-8)
    scaled = np.clip(pulse / np.maximum(envelope, floor), -3, 3)
    features = [RATES, distances.min(axis=1), np.mean(distances <= 5, axis=1), np.median(distances, axis=1)]

    def append_channels(values):
        features.extend((values.max(axis=1), values.mean(axis=1), values.min(axis=1)))

    for support in spectral_support(scaled, fs) + spectral_support(pulse, fs, (1,)):
        append_channels(support)
    left = spectral_support(scaled[:len(scaled) // 2], fs, (1,))[0]
    right = spectral_support(scaled[len(scaled) // 2:], fs, (1,))[0]
    append_channels(np.minimum(left, right))
    for multiple in (1, 0.5, 2):
        append_channels(lag_agreement(scaled, fs, multiple))
    color_support = (spectral_support((scaled[:, 1] - scaled[:, 0])[:, None], fs, (1,))[0]
                     if waves.shape[1] == 3 else np.full((len(RATES), 1), np.nan))
    append_channels(color_support)
    return np.column_stack(features)


def fit_rate_model(features, reference, *, max_iter=55):
    good = np.abs(RATES - reference[:, None]) <= TOLERANCE
    model = HistGradientBoostingClassifier(max_iter=max_iter, max_leaf_nodes=14, min_samples_leaf=70,
                                           l2_regularization=6, early_stopping=False, random_state=42)
    return model.fit(features.reshape(-1, features.shape[-1]), good.ravel())


def predict_rates(model, features):
    probabilities = model.predict_proba(features.reshape(-1, features.shape[-1]))[:, 1].reshape(len(features), -1)
    best = probabilities.argmax(axis=1)
    neighborhood = np.abs(RATES[best, None] - RATES) <= 9
    weights = probabilities**2 * neighborhood
    return (weights @ RATES) / weights.sum(axis=1), probabilities[np.arange(len(features)), best]


def group_predictions(features, reference, people, *, max_iter=55):
    bpm, score = np.empty((2, len(features)))
    folds = np.empty(len(features), dtype=int)
    with threadpool_limits(limits=1):
        for fold, (train, test) in enumerate(GroupKFold(6).split(features, reference, people)):
            model = fit_rate_model(features[train], reference[train], max_iter=max_iter)
            bpm[test], score[test] = predict_rates(model, features[test])
            folds[test] = fold + 1
    return bpm, score, folds


def refine(peak_rate, peak_score, periodic_rate, periodic_score):
    if abs(periodic_rate - peak_rate) <= AGREEMENT_BPM:
        return (peak_rate * peak_score + periodic_rate * periodic_score) / (peak_score + periodic_score)
    return periodic_rate if periodic_score > peak_score else peak_rate


def main():
    source = development_rows()
    features = []
    with zipfile.ZipFile(ROOT / "data/butppg-2.0.0.zip") as archive:
        prefix = next(name.rsplit("/", 1)[0] + "/" for name in archive.namelist()
                      if name.endswith("/subject-info.csv"))
        for row in source:
            waves, fs = read_wave(archive, prefix, row["id"], "PPG", all_ppg_channels=True)
            features.append(rate_features(waves, fs))
    reference = np.array([float(r["qrs_bpm"]) for r in source])
    people = np.array([r["person"] for r in source])
    periodic_rates, scores, folds = group_predictions(np.array(features), reference, people)
    rows = []
    for r, ref, periodic_rate, score, fold in zip(source, reference, periodic_rates, scores, folds):
        old_bpm = float(r["candidate_bpm"])
        retry = r["candidate"].startswith("retry_")
        updated_bpm = old_bpm if retry else refine(old_bpm, float(r["confidence"]), periodic_rate, score)
        rows.append(dict(id=r["id"], person=r["person"], fold=fold, qrs_bpm=ref, prior_bpm=old_bpm,
                         prior_score=float(r["confidence"]), periodic_bpm=periodic_rate, periodic_score=score,
                         refined_bpm=updated_bpm, prior_outcome=outcome(old_bpm, ref, retry),
                         refined_outcome=outcome(updated_bpm, ref, retry)))
    write_table("refined-rates.csv", rows)

    old = counts([r["prior_outcome"] for r in rows])
    new = counts([r["refined_outcome"] for r in rows])
    assert old == dict(show_bad=411, show_good=747, retry_bad=310, retry_good=72, missing=0)
    fixed = sum(r["prior_outcome"] == "show_bad" and r["refined_outcome"] == "show_good" for r in rows)
    regressed = sum(r["prior_outcome"] == "show_good" and r["refined_outcome"] == "show_bad" for r in rows)
    report = dict(records=len(rows), people=len(set(people)), prior=old, refined=new,
                  prior_displayed_errors_corrected=fixed, prior_displayed_good_now_wrong=regressed,
                  per_100={label: {k: n * 100 / len(rows) for k, n in totals.items()}
                           for label, totals in [("prior", old), ("refined", new)]})
    text = json.dumps(report, indent=2)
    (OUT / "refined-rates-summary.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
