"""Paired development experiment. Run baseline.py first to create the frozen manifest."""
import csv
import json
import zipfile

import numpy as np
from scipy.signal import detrend, periodogram
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import LeaveOneGroupOut

from baseline import ROOT, OUT, estimate, read_wave, write_table

TOLERANCE = 5.0
RETRY_TARGET = 0.30


def spectrum(signal, fs):
    freq, power = periodogram(detrend(signal), fs, window="hann", nfft=4096,
                              detrend=False, scaling="spectrum")
    band = (freq >= 0.6) & (freq <= 200 / 60)
    return freq[band], power[band]


def spectral_estimate(wave, fs, peak_bpm):
    freq, power = spectrum(wave, fs)
    index = np.argmax(power)
    if power[index] <= 0 or np.ptp(wave) == 0:
        raise ValueError("No measurable spectral power")
    center = freq[index]
    bpm = float(60 * center)
    concentration = power[np.abs(freq - center) <= 0.15].sum() / power.sum()
    halves = []
    for half in np.array_split(wave, 2):
        half_freq, half_power = spectrum(half, fs)
        halves.append(60 * half_freq[np.argmax(half_power)])
    features = [concentration, abs(halves[0] - halves[1]),
                abs(bpm - peak_bpm) if peak_bpm is not None else 200.0,
                np.log1p(np.ptp(wave)), np.mean(np.diff(wave) == 0), bpm]
    return bpm, features


def load_csv(filename):
    with (OUT / filename).open(newline="") as file:
        return list(csv.DictReader(file))


def score_quality(features, good, people):
    """Return per-person out-of-fold scores and thresholds learned on other people."""
    n = len(good)
    probability, threshold, simple_threshold = np.empty((3, n))
    for train, test in LeaveOneGroupOut().split(features, good, people):
        # OOB probabilities reduce optimism when choosing the training-fold cutoff.
        model = RandomForestClassifier(n_estimators=160, min_samples_leaf=20, max_depth=5,
                                       random_state=42, oob_score=True, n_jobs=2)
        model.fit(features[train], good[train])
        probability[test] = model.predict_proba(features[test])[:, 1]
        threshold[test] = np.quantile(model.oob_decision_function_[:, 1], RETRY_TARGET)
        simple_threshold[test] = np.quantile(features[train, 0], RETRY_TARGET)
    return probability, threshold, simple_threshold


def tally(retry, good):
    return dict(blocked_bad=int(sum(retry & ~good)), blocked_good=int(sum(retry & good)),
                shown_bad=int(sum(~retry & ~good)), shown_good=int(sum(~retry & good)))


def describe(errors):
    return dict(estimated=int(np.isfinite(errors).sum()), within_5=int(sum(errors <= TOLERANCE)),
                outside_5=int(sum(errors > TOLERANCE)), mae=float(np.nanmean(errors)),
                median=float(np.nanmedian(errors)))


def main():
    dev = load_csv("development-baseline.csv")
    manifest = load_csv("fingertip-manifest.csv")
    assert [(r["id"], r["person"]) for r in dev] == [
        (r["id"], r["person"]) for r in manifest if r["split"] == "development"]
    features, rows = [], []
    with zipfile.ZipFile(ROOT / "data/butppg-2.0.0.zip") as archive:
        prefix = next(n for n in archive.namelist() if n.endswith("/subject-info.csv")).rsplit("/", 1)[0] + "/"
        for r in dev:
            wave, fs = read_wave(archive, prefix, r["id"], "PPG")
            peak, _, _ = estimate(wave, fs)
            assert peak == (float(r["ppg_bpm"]) if r["ppg_bpm"] else None)
            bpm, x = spectral_estimate(wave, fs, peak)
            ref = float(r["ecg_bpm"])
            rows.append(dict(id=r["id"], person=r["person"], ecg_bpm=ref, peak_bpm=peak,
                             spectral_bpm=bpm, spectral_error=abs(bpm - ref)))
            features.append(x)
    x = np.array(features)
    errors = np.array([r["spectral_error"] for r in rows])
    good = errors <= TOLERANCE
    people = np.array([r["person"] for r in rows])
    prob, cutoff, simple_cutoff = score_quality(x, good, people)
    retry = prob < cutoff
    simple_retry = x[:, 0] < simple_cutoff
    for i, r in enumerate(rows):
        r.update(quality_score=prob[i], quality_cutoff=cutoff[i], retry=int(retry[i]),
                 spectral_concentration=x[i, 0], simple_retry=int(simple_retry[i]))
    base = np.array([float(r["error_bpm"]) if r["error_bpm"] else np.nan for r in dev])
    valid = np.isfinite(base)
    peak_good = base[valid] <= TOLERANCE
    peak_x = np.column_stack((x[valid], [r["peak_bpm"] for r in rows if r["peak_bpm"] is not None]))
    peak_prob, peak_cutoff, _ = score_quality(peak_x, peak_good, people[valid])
    peak_retry = peak_prob < peak_cutoff
    for r in rows:
        r.update(peak_quality_score=None, peak_quality_cutoff=None, peak_retry=1)
    for index, score, threshold in zip(np.flatnonzero(valid), peak_prob, peak_cutoff):
        rows[index].update(peak_quality_score=score, peak_quality_cutoff=threshold,
                           peak_retry=int(score < threshold))
    write_table("quality-comparison.csv", rows)
    summary = dict(records=len(rows), people=len(set(people)), peak=describe(base),
                   spectrum=describe(errors), spectrum_on_paired=describe(errors[np.isfinite(base)]),
                   gate=tally(retry, good), concentration_gate=tally(simple_retry, good),
                   peak_gate=tally(peak_retry, peak_good), peak_unavailable=int(sum(~valid)),
                   mae_shown=float(np.mean(errors[~retry])))
    assert sum(summary["gate"].values()) == len(rows)
    report = json.dumps(summary, indent=2)
    (OUT / "quality-summary.json").write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
