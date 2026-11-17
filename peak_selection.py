"""Compare PPG peak candidates and calibrate an abstention rule on development participants."""
import argparse
import json
import zipfile
from collections import Counter

import numpy as np
from scipy.ndimage import median_filter, maximum_filter1d
from scipy.signal import butter, find_peaks, sosfiltfilt
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from threadpoolctl import threadpool_limits

from adaptive_peaks import outcome, counts
from baseline import OUT, ROOT, read_wave, write_table
from compare_quality import TOLERANCE, load_csv, spectrum
from reference_audit import qrs_rate

RETRY_TARGETS = (0.20, 0.23, 0.25, 0.30)


def target_key(target):
    return f"retry_{int(100 * target)}"


def peak_candidates(waves, fs):
    sos = butter(3, [0.65, 3.5], fs=fs, btype="bandpass", output="sos")
    candidates = []
    for channel, wave in enumerate(waves.T):
        pulse = sosfiltfilt(sos, wave)
        envelope = median_filter(abs(pulse), size=2 * fs + 1, mode="nearest")
        floor = max(np.median(abs(pulse)) * 0.12, 1e-10)
        scaled = pulse / np.maximum(envelope, floor)
        local_range = maximum_filter1d(scaled, fs + 1) + maximum_filter1d(-scaled, fs + 1)
        freq, power = spectrum(pulse, fs)
        spectrum_bpm = freq[power.argmax()] * 60
        for polarity in (1, -1):
            trace = polarity * scaled
            peaks, props = find_peaks(trace, distance=int(np.ceil(0.30 * fs)),
                                      prominence=np.maximum(0.25, 0.22 * local_range))
            if len(peaks) < 3:
                continue
            a, b, c = trace[peaks - 1], trace[peaks], trace[peaks + 1]
            offset = np.clip(0.5 * (a - c) / (a - 2 * b + c - 1e-12), -0.5, 0.5)
            intervals = np.diff(peaks + offset) / fs
            period = np.median(intervals)
            bpm = float(60 / period)
            lag = max(1, round(fs * period))
            first, second = pulse[:-lag], pulse[lag:]
            correlation = np.dot(first, second) / max(np.linalg.norm(first) * np.linalg.norm(second), 1e-16)
            spectral_support = power[np.abs(freq - 1 / period) <= 0.15].sum() / max(power.sum(), 1e-16)
            features = [channel, polarity, bpm, len(peaks) * 6 - bpm,
                        np.median(abs(intervals - period)) / period,
                        np.mean(abs(intervals - period) > 0.20 * period),
                        np.median(props["prominences"]), correlation, spectral_support,
                        abs(bpm - spectrum_bpm), np.log1p(np.ptp(wave)),
                        np.mean(np.diff(wave) == 0)]
            candidates.append((bpm, channel, polarity, features))
    for bpm, _, _, features in candidates:
        other = [candidate[0] for candidate in candidates if candidate[3] is not features]
        features.extend([sum(abs(bpm - rate) <= 5 for rate in other),
                         min((abs(bpm - rate) for rate in other), default=200.)])
    return candidates


def best_candidates(model, features, window_indices):
    scores = model.predict_proba(features)[:, 1]
    best = {}
    for i, (window, score) in enumerate(zip(window_indices, scores)):
        if window not in best or score > best[window][1]:
            best[window] = (i, score)
    return best


def train_model(x, good):
    model = HistGradientBoostingClassifier(max_iter=80, max_leaf_nodes=12,
                                           min_samples_leaf=45, l2_regularization=5.0,
                                           random_state=42, early_stopping=False)
    return model.fit(x, good)


def grouped_validation_scores(x, good, windows, people):
    scores = []
    for fit, val in GroupKFold(4).split(x, good, people):
        model = train_model(x[fit], good[fit])
        scores.extend(score for _, score in best_candidates(model, x[val], windows[val]).values())
    return scores


def cross_validate(x, good, windows, people):
    predictions = {}
    splitter = LeaveOneGroupOut()
    with threadpool_limits(limits=1):
        for train, test in splitter.split(x, good, people):
            validation_scores = grouped_validation_scores(x[train], good[train], windows[train], people[train])
            thresholds = np.quantile(validation_scores, RETRY_TARGETS)
            model = train_model(x[train], good[train])
            for window, (i, score) in best_candidates(model, x[test], windows[test]).items():
                predictions[window] = (test[i], float(score), thresholds)
    return predictions


def audit_misses(rows):
    misses = [row for row in rows if row["new"] == "show_bad"]
    assert len(misses) == 624
    deviation = np.array([float(row["new_bpm"]) - float(row["ecg_bpm"]) for row in misses])
    diff = np.array([int(row["new_peaks"]) - int(row["ecg_beats"]) for row in misses])
    return dict(total=len(misses), below_ecg=int(sum(deviation < 0)), above_ecg=int(sum(deviation > 0)),
                median_abs_error=float(np.median(abs(deviation))), fewer_peaks=int(sum(diff < 0)),
                more_peaks=int(sum(diff > 0)), equal_peaks=int(sum(diff == 0)),
                rest=sum(r["motion"] == "0" for r in misses),
                dataset_low_quality=sum(r["quality_annotation"] == "0" for r in misses),
                outcomes=counts([r["candidate"] for r in misses]))


def compare_references(rows):
    results = {}
    for name, group, reference in [
        ("qrs_all", rows, "qrs_bpm"),
        ("csv_qrs_agree", [r for r in rows if abs(float(r["ecg_bpm"]) - r["qrs_bpm"]) <= TOLERANCE],
         "ecg_bpm"),
    ]:
        prior = [outcome(float(r["new_bpm"]), float(r[reference]), r["new"].startswith("retry"))
                 for r in group]
        candidate = [outcome(r["candidate_bpm"], float(r[reference]), r["candidate"].startswith("retry"))
                     for r in group]
        results[name] = dict(records=len(group), prior=counts(prior), candidate=counts(candidate))
    return results


def main(training_reference, primary_target):
    rows = load_csv("adaptive-peaks.csv")
    manifest = load_csv("fingertip-manifest.csv")
    assert [(r["id"], r["person"]) for r in rows] == [
        (r["id"], r["person"]) for r in manifest if r["split"] == "development"
    ]
    features, correct, people, windows, bpm, channel, polarity = [], [], [], [], [], [], []
    with zipfile.ZipFile(ROOT / "data/butppg-2.0.0.zip") as archive:
        prefix = next(n for n in archive.namelist() if n.endswith("/subject-info.csv")).rsplit("/", 1)[0] + "/"
        for i, row in enumerate(rows):
            record = row["id"]
            row["qrs_bpm"] = qrs_rate(archive.read(f"{prefix}{record}/{record}.qrs"))
            waves, fs = read_wave(archive, prefix, row["id"], "PPG", all_ppg_channels=True)
            for rate, color, sign, x in peak_candidates(waves, fs):
                features.append(x)
                correct.append(abs(rate - float(row[training_reference])) <= TOLERANCE)
                people.append(row["person"])
                windows.append(i)
                bpm.append(rate)
                channel.append("RGB"[color])
                polarity.append(sign)
    predictions = cross_validate(np.array(features), np.array(correct), np.array(windows), np.array(people))
    for i, row in enumerate(rows):
        row.update(candidate_bpm=None, channel=None, polarity=None, confidence=None)
        if i in predictions:
            j, score, thresholds = predictions[i]
            row.update(candidate_bpm=bpm[j], channel=channel[j], polarity=polarity[j], confidence=score)
        for k, target in enumerate(RETRY_TARGETS):
            key = target_key(target)
            threshold = float(thresholds[k]) if i in predictions else None
            row[key + "_threshold"] = threshold
            row[key + "_outcome"] = outcome(row["candidate_bpm"], float(row["ecg_bpm"]),
                                            threshold is not None and score < threshold)
        row["candidate"] = row[target_key(primary_target) + "_outcome"]
    filename = "peak-selection" if training_reference == "ecg_bpm" else "peak-selection-qrs"
    write_table(filename + ".csv", rows)
    old = counts([r["new"] for r in rows])
    sensitivity = {str(target): counts([r[target_key(target) + "_outcome"] for r in rows])
                   for target in RETRY_TARGETS}
    raw_candidates = counts([outcome(r["candidate_bpm"], float(r["ecg_bpm"]), False) for r in rows])
    prior_good = [r for r in rows if r["new"] in {"show_good", "retry_good"}]
    report = dict(records=len(rows), people=len(set(people)), training_reference=training_reference,
                  prior=old, primary_retry_target=primary_target,
                  candidate=sensitivity[str(primary_target)], retry_target_results=sensitivity,
                  candidate_before_quality_gate=raw_candidates,
                  selected_channel=dict(Counter(r["channel"] for r in rows)),
                  accepted_error_audit=audit_misses(rows),
                  prior_good_outcomes=counts([r["candidate"] for r in prior_good]),
                  prior_good_by_target={str(target): counts([r[target_key(target) + "_outcome"] for r in prior_good])
                                        for target in RETRY_TARGETS},
                  reference_sensitivity=compare_references(rows))
    text = json.dumps(report, indent=2)
    (OUT / (filename + "-summary.json")).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-reference", choices=("ecg_bpm", "qrs_bpm"), default="ecg_bpm")
    parser.add_argument("--retry-target", type=float, choices=RETRY_TARGETS, default=0.23)
    args = parser.parse_args()
    main(args.training_reference, args.retry_target)
