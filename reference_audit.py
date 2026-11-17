"""Cross-check published heart rates against the ECG beat annotations in BUT PPG 2.0.0."""
import json
import zipfile
from collections import Counter

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

from baseline import OUT, ROOT, read_wave, write_table
from compare_quality import TOLERANCE, load_csv


def qrs_times(payload):
    """Decode ECG sample indices from BUT PPG's WFDB beat annotations."""
    words = np.frombuffer(payload, dtype="<u2")
    beats = []
    sample = index = 0
    while index < len(words):
        word = int(words[index])
        index += 1
        if word == 0:
            break
        code = word >> 10
        if code == 59:  # SKIP stores a signed 32-bit delta, high word first.
            high, low = words[index:index + 2]
            delta = (int(high) << 16) | int(low)
            sample += delta if delta < 2**31 else delta - 2**32
            index += 2
        elif code == 1:  # Normal beat
            sample += word & 1023
            beats.append(sample)
        else:
            raise ValueError(f"Unexpected BUT PPG QRS annotation type {code}")
    times = np.asarray(beats, dtype=np.int64)
    if times.size < 2 or times[0] < 0 or np.any(np.diff(times) <= 0):
        raise ValueError("Expected at least two strictly increasing ECG beat times")
    return times


def qrs_rate(payload, fs=1000):
    """Return the median of the instantaneous heart rates between annotated beats."""
    return float(np.median(60 * fs / np.diff(qrs_times(payload))))


def inspect_ecg(archive, prefix, row):
    record = row["id"]
    ecg, fs = read_wave(archive, prefix, record, "ECG")
    beat_times = qrs_times(archive.read(f"{prefix}{record}/{record}.qrs"))
    filtered = sosfiltfilt(butter(3, [5, 35], fs=fs, btype="bandpass", output="sos"), ecg)
    magnitude = np.abs(filtered)
    peaks, _ = find_peaks(magnitude, distance=0.30 * fs,
                          prominence=0.35 * np.percentile(magnitude, 99))
    if peaks.size < 2:
        return dict(id=record, csv_bpm=row["csv_bpm"], qrs_bpm=row["qrs_bpm"],
                    independent_ecg_bpm=None, max_qrs_distance_ms=None,
                    detected_ecg_peaks=int(peaks.size), annotated_ecg_peaks=int(beat_times.size))
    distances_ms = np.min(np.abs(beat_times[:, None] - peaks), axis=1) * 1000 / fs
    return dict(id=record, csv_bpm=row["csv_bpm"], qrs_bpm=row["qrs_bpm"],
                independent_ecg_bpm=float(np.median(60 * fs / np.diff(peaks))),
                max_qrs_distance_ms=float(distances_ms.max()),
                detected_ecg_peaks=int(peaks.size), annotated_ecg_peaks=int(beat_times.size))


def main():
    previous = load_csv("adaptive-peaks.csv")
    manifest = load_csv("fingertip-manifest.csv")
    assert [row["id"] for row in previous] == [
        row["id"] for row in manifest if row["split"] == "development"
    ]
    rows = []
    with zipfile.ZipFile(ROOT / "data/butppg-2.0.0.zip") as archive:
        prefix = next(name for name in archive.namelist()
                      if name.endswith("/subject-info.csv")).rsplit("/", 1)[0] + "/"
        for row in previous:
            record = row["id"]
            payload = archive.read(f"{prefix}{record}/{record}.qrs")
            times = qrs_times(payload)
            assert times.size == int(row["ecg_beats"]) and times[-1] < 10_000
            annotated_bpm = qrs_rate(payload)
            csv_bpm = float(row["ecg_bpm"])
            adaptive_bpm = float(row["new_bpm"])
            rows.append(dict(id=record, person=row["person"], csv_bpm=csv_bpm,
                             qrs_bpm=annotated_bpm, reference_gap=abs(csv_bpm - annotated_bpm),
                             motion=row["motion"], quality_annotation=row["quality_annotation"],
                             adaptive_peaks=int(row["new_peaks"]), qrs_count=int(times.size),
                             adaptive_bpm=adaptive_bpm, adaptive_status=row["new"],
                             adaptive_error_vs_qrs=abs(adaptive_bpm - annotated_bpm)))
        disagreement = [row for row in rows if row["reference_gap"] > TOLERANCE]
        failed = [row for row in rows if row["adaptive_status"] == "show_bad"]
        checked_ids = {max(disagreement, key=lambda row: row["reference_gap"])["id"],
                       "144059", "132056"}
        checked_rows = [row for row in rows if row["id"] in checked_ids
                        or row["reference_gap"] > TOLERANCE]
        waveform_checks = [inspect_ecg(archive, prefix, row) for row in checked_rows]
    write_table("reference-audit.csv", rows)
    write_table("reference-waveform-checks.csv", waveform_checks)
    discordant_ids = {row["id"] for row in disagreement}
    verified = [row for row in waveform_checks if row["id"] in discordant_ids
                and row["independent_ecg_bpm"] is not None]
    directions = Counter("low" if row["adaptive_bpm"] < row["csv_bpm"] else "high" for row in failed)
    peak_counts = Counter(np.sign(row["adaptive_peaks"] - row["qrs_count"]) for row in failed)
    summary = dict(records=len(rows), reference_gap_over_5=len(disagreement),
                   affected_people=Counter(row["person"] for row in disagreement),
                   adaptive_failures=len(failed),
                   failure_details=dict(bpm_direction=dict(directions), fewer_peaks=peak_counts[-1],
                                        matching_count=peak_counts[0], more_peaks=peak_counts[1],
                                        at_rest=sum(row["motion"] == "0" for row in failed),
                                        quality_label_0=sum(row["quality_annotation"] == "0" for row in failed),
                                        abs_error_median=float(np.median([
                                            abs(row["adaptive_bpm"] - row["csv_bpm"]) for row in failed
                                        ]))),
                   adaptive_failures_with_reference_gap=sum(
                       row["reference_gap"] > TOLERANCE for row in failed),
                   adaptive_failures_within_5_of_qrs=sum(
                       row["adaptive_error_vs_qrs"] <= TOLERANCE for row in failed),
                   discordant_waveform_validation=dict(
                       available=len(verified),
                       within_5_of_qrs=sum(abs(row["independent_ecg_bpm"] - row["qrs_bpm"]) <= TOLERANCE
                                           for row in verified),
                       within_5_of_csv=sum(abs(row["independent_ecg_bpm"] - row["csv_bpm"]) <= TOLERANCE
                                           for row in verified),
                       all_peaks_within_10_ms=sum(row["detected_ecg_peaks"] == row["annotated_ecg_peaks"]
                                                 and row["max_qrs_distance_ms"] <= 10 for row in verified)),
                   waveform_examples=[row for row in waveform_checks if row["id"] in checked_ids])
    report = json.dumps(summary, indent=2)
    (OUT / "reference-audit-summary.json").write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
