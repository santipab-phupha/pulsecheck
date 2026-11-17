"""Audit accepted errors and compare an adaptive red-PPG peak counter on the frozen development set."""
import json
import zipfile

import numpy as np
from scipy.ndimage import median_filter, maximum_filter1d
from scipy.signal import butter, find_peaks, sosfiltfilt

from baseline import OUT, ROOT, read_wave, read_index, write_table
from compare_quality import TOLERANCE, load_csv, score_quality, spectral_estimate


def adaptive_peaks(wave, fs):
    sos = butter(3, [0.65, 3.5], fs=fs, btype="bandpass", output="sos")
    pulse = sosfiltfilt(sos, wave)
    # Cap each transient's influence on the envelope to its local neighborhood.
    envelope = median_filter(abs(pulse), size=2 * fs + 1, mode="nearest")
    floor = max(np.median(abs(pulse)) * 0.12, 1e-10)
    scaled = pulse / np.maximum(envelope, floor)
    local_range = maximum_filter1d(scaled, fs + 1) + maximum_filter1d(-scaled, fs + 1)
    peaks, _ = find_peaks(scaled, distance=int(np.ceil(0.30 * fs)),
                          prominence=np.maximum(0.25, 0.22 * local_range))
    if len(peaks) < 3:
        return None, len(peaks)
    # Parabolic sub-sample peak times reduce rounding of short inter-beat intervals.
    a, b, c = scaled[peaks - 1], scaled[peaks], scaled[peaks + 1]
    offset = np.clip(0.5 * (a - c) / (a - 2 * b + c - 1e-12), -0.5, 0.5)
    return float(60 * fs / np.median(np.diff(peaks + offset))), len(peaks)


def qrs_count(payload):
    # These BUT PPG annotations contain normal-beat events and optional long time skips.
    words = np.frombuffer(payload, dtype="<u2")
    i = count = 0
    while i < len(words):
        word = int(words[i])
        i += 1
        if word == 0:
            break
        code = word >> 10
        if code == 59:
            i += 2
        elif code == 1:
            count += 1
        else:
            raise ValueError(f"Unexpected QRS annotation type {code}")
    return count


def outcome(bpm, ref, retry):
    if bpm is None:
        return "missing"
    good = abs(bpm - ref) <= TOLERANCE
    return ("retry_" if retry else "show_") + ("good" if good else "bad")


def counts(outcomes):
    return {key: outcomes.count(key) for key in ("show_bad", "show_good", "retry_bad", "retry_good", "missing")}


def main():
    prior = load_csv("quality-comparison.csv")
    baseline = {r["id"]: r for r in load_csv("development-baseline.csv")}
    manifest = load_csv("fingertip-manifest.csv")
    assert [r["id"] for r in prior] == [r["id"] for r in manifest if r["split"] == "development"]
    rows, features = [], []
    with zipfile.ZipFile(ROOT / "data/butppg-2.0.0.zip") as z:
        prefix = next(n for n in z.namelist() if n.endswith("/subject-info.csv")).rsplit("/", 1)[0] + "/"
        labels = read_index(z, prefix, "quality-hr-ann.csv")
        for r in prior:
            rec = r["id"]
            old = float(r["peak_bpm"]) if r["peak_bpm"] else None
            ref = float(r["ecg_bpm"])
            wave, fs = read_wave(z, prefix, rec, "PPG")
            new, n_peaks = adaptive_peaks(wave, fs)
            _, x = spectral_estimate(wave, fs, new)
            features.append(x + [new if new is not None else 0.0])
            rows.append(dict(id=rec, person=r["person"], motion=baseline[rec]["motion"],
                             quality_annotation=labels[rec]["Quality"], ecg_bpm=ref,
                             ecg_beats=qrs_count(z.read(f"{prefix}{rec}/{rec}.qrs")),
                             old_peaks=int(baseline[rec]["peaks"]), old_bpm=old,
                             old=outcome(old, ref, int(r["peak_retry"])), new_peaks=n_peaks, new_bpm=new))
    valid = np.array([r["new_bpm"] is not None for r in rows])
    good = np.array([abs(r["new_bpm"]-r["ecg_bpm"]) <= TOLERANCE for r in rows if r["new_bpm"] is not None])
    people = np.array([r["person"] for r in rows])
    prob, cutoff, _ = score_quality(np.asarray(features)[valid], good, people[valid])
    for r in rows:
        r.update(score=None, cutoff=None, new="missing")
    for idx, score, threshold in zip(np.flatnonzero(valid), prob, cutoff):
        r = rows[idx]
        r.update(score=score, cutoff=threshold, new=outcome(r["new_bpm"], r["ecg_bpm"], score < threshold))
    write_table("adaptive-peaks.csv", rows)
    misses = [r for r in rows if r["old"] == "show_bad"]
    peak_diff = np.array([r["old_peaks"] - r["ecg_beats"] for r in misses])
    old_counts = counts([r["old"] for r in rows])
    new_counts = counts([r["new"] for r in rows])
    assert len(misses) == 696 and len(rows) == sum(new_counts.values()) == 1540
    def retry_count(c):
        return len(rows) - c["show_bad"] - c["show_good"]
    fixed_shown = [r for r in rows if r["old"].startswith("show_") and r["new_bpm"] is not None]
    summary = dict(records=len(rows), subjects=len(set(people)),
                   old=old_counts, new=new_counts,
                   new_on_old_accepts=dict(available=len(fixed_shown),
                       outside_5=sum(abs(r["new_bpm"]-r["ecg_bpm"]) > TOLERANCE for r in fixed_shown)),
                   old_bad_high=sum(r["old_bpm"] > r["ecg_bpm"] for r in misses),
                   old_bad_low=sum(r["old_bpm"] < r["ecg_bpm"] for r in misses),
                   old_bad_rest=sum(r["motion"]=="0" for r in misses),
                   old_bad_low_quality=sum(r["quality_annotation"]=="0" for r in misses),
                   old_bad_fewer_peaks=int(sum(peak_diff < 0)), old_bad_same_count=int(sum(peak_diff==0)),
                   median_peak_deficit=float(-np.median(peak_diff)),
                   old_errors_now=counts([r["new"] for r in misses]),
                   bad_displays_prevented_per_100=100*(old_counts["show_bad"]-new_counts["show_bad"])/len(rows),
                   additional_retries_per_100=100*(retry_count(new_counts)-retry_count(old_counts))/len(rows))
    report=json.dumps(summary, indent=2)
    (OUT / "adaptive-summary.json").write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
