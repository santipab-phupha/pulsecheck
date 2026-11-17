"""PulseCheck development baseline on BUT PPG 2.0.0. Run from any directory."""
import csv
import io
import json
import re
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
MOTION = {"0": "rest", "1": "increased pressure", "2": "finger movement", "3": "walking",
          "4": "coughing", "5": "laughing", "6": "changing light", "7": "talking", "2;3": "movement + walking"}


def write_table(name, rows):
    with (OUT / name).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def read_index(archive, prefix, file):
    text = archive.read(prefix + file).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    index = {r["ID"]: r for r in rows}
    assert len(index) == len(rows), "Repeated recording ID"
    return index


def read_wave(archive, prefix, record, kind, *, all_ppg_channels=False):
    base = f"{prefix}{record}/{record}_{kind}"
    lines = archive.read(base + ".hea").decode().splitlines()
    channels, fs, frames = map(int, lines[0].split()[1:4])
    fields = [line.split() for line in lines[1:1 + channels]]
    dtype = {"16": "<i2", "32": "<i4"}[fields[0][1]]
    raw = np.frombuffer(archive.read(base + ".dat"), dtype).reshape(frames, channels)
    def calibration(field):
        match = re.fullmatch(r"([^()]+)\(([-+]?\d+)\)/.+", field[2])
        return float(match[1]), int(match[2])
    if frames == 1:  # Original cohort stores each time point with its own gain/offset.
        gains, offsets = np.array([calibration(f) for f in fields]).T
        signal = (raw[0].astype(float) - offsets) / gains
    else:
        if kind == "PPG":
            assert fields[0][-1] == "PPG_R"
            if all_ppg_channels:
                gains, offsets = np.array([calibration(f) for f in fields]).T
                signals = -(raw.astype(float) - offsets) / gains
                assert len(signals) == 10 * fs and np.isfinite(signals).all()
                return signals, fs
        gain, offset = calibration(fields[0])
        signal = (raw[:, 0].astype(float) - offset) / gain
        if kind == "PPG":
            signal = -signal  # Invert red intensity, as in the original single-channel release.
    assert signal.size == 10 * fs and np.isfinite(signal).all()
    return (signal[:, None] if all_ppg_channels else signal), fs


def estimate(wave, fs):
    band = butter(3, [0.6, 4.0], btype="bandpass", fs=fs, output="sos")
    filtered = sosfiltfilt(band, wave)
    prominence = 0.35 * (np.percentile(filtered, 95) - np.percentile(filtered, 5))
    peaks, _ = find_peaks(filtered, distance=int(np.ceil(0.30 * fs)), prominence=prominence)
    bpm = float(60 * fs / np.median(np.diff(peaks))) if len(peaks) >= 3 else None
    return bpm, filtered, peaks


def examples(archive, prefix, rows):
    fig, axes = plt.subplots(2, 2, figsize=(13, 6.3), sharex=True, layout="constrained")
    cases = []
    for col, (motion, good) in enumerate([("0", True), ("2", False)]):
        pool = [r for r in rows if r["motion"] == motion and r["error_bpm"] is not None
                and (r["error_bpm"] <= 5) == good]
        pool.sort(key=lambda r: (r["error_bpm"], r["id"]))
        row = pool[len(pool) // 2]
        cases.append(row)
        wave, fs = read_wave(archive, prefix, row["id"], "PPG")
        ecg, hz = read_wave(archive, prefix, row["id"], "ECG")
        bpm, filtered, peaks = estimate(wave, fs)
        ax, ref = axes[:, col]
        ax.plot(np.arange(len(wave)) / fs, filtered, color="#126a79", lw=1.6)
        ax.scatter(peaks / fs, filtered[peaks], color="#c94a25", s=20, label="Detected peaks", zorder=3)
        ax.legend(fontsize=8, loc="lower right")
        ax.set_title(f"{'Within tolerance' if good else 'Outside tolerance'}   |   {MOTION[motion]}   |   {row['id']}\n"
                     f"PPG {bpm:.1f} bpm     /     ECG {row['ecg_bpm']:.0f} bpm     /     Error {row['error_bpm']:.1f} bpm",
                     loc="left", fontsize=11, pad=12)
        # Remove slow baseline drift for display only. Reference HR comes from the annotations.
        ecg_display = sosfiltfilt(butter(2, 0.5, btype="highpass", fs=hz, output="sos"), ecg)
        ref.plot(np.arange(len(ecg)) / hz, ecg_display, color="#384764", lw=0.75)
        ref.set_xlabel("Time (s)")
        ax.set_ylabel("Filtered PPG (a.u.)")
        ref.set_ylabel("ECG, drift removed (µV)")
        for panel in (ax, ref):
            panel.set_xlim(0, 10)
            panel.grid(alpha=0.17)
            panel.spines[["right", "top"]].set_visible(False)
    fig.suptitle("PulseCheck   /   Fingertip readings compared with simultaneous ECG", fontsize=16)
    fig.savefig(OUT / "baseline-cases.png", dpi=150)
    plt.close(fig)
    return cases


def main():
    OUT.mkdir(exist_ok=True)
    with zipfile.ZipFile(ROOT / "data/butppg-2.0.0.zip") as archive:
        prefix = next(n for n in archive.namelist() if n.endswith("/subject-info.csv")).rsplit("/", 1)[0] + "/"
        metadata = read_index(archive, prefix, "subject-info.csv")
        labels = read_index(archive, prefix, "quality-hr-ann.csv")
        assert metadata.keys() == labels.keys()
        ids = sorted(i for i, r in metadata.items() if r["Ear/finger"] == "1")
        people = sorted({i[:3] for i in ids})
        rng = np.random.default_rng(42)
        held = set()
        for cohort, size in [([p for p in people if int(p) < 112], 2),
                             ([p for p in people if int(p) >= 112], 4)]:
            held.update(rng.choice(cohort, size=size, replace=False))
        write_table("fingertip-manifest.csv", [{"id": i, "person": i[:3],
                    "split": "holdout" if i[:3] in held else "development"} for i in ids])
        rows = []
        for i in ids:
            if i[:3] in held:
                continue
            wave, fs = read_wave(archive, prefix, i, "PPG")
            bpm, _, peaks = estimate(wave, fs)
            ref = float(labels[i]["HR"])
            assert np.isfinite(ref) and ref > 0
            rows.append(dict(id=i, person=i[:3], motion=metadata[i]["Motion"], peaks=len(peaks),
                             ppg_bpm=bpm, ecg_bpm=ref, error_bpm=None if bpm is None else abs(bpm-ref)))
        write_table("development-baseline.csv", rows)
        cases = examples(archive, prefix, rows)
    errors = np.array([r["error_bpm"] for r in rows if r["error_bpm"] is not None])
    summary = dict(fingertip_records=len(ids), people=len(people), holdout_people=sorted(held),
                   holdout_records=len(ids)-len(rows), development_people=len(people)-len(held),
                   development_records=len(rows), estimated=len(errors), no_estimate=len(rows)-len(errors),
                   within_5=int(np.sum(errors<=5)), over_5=int(np.sum(errors>5)),
                   mae_bpm=float(errors.mean()), median_error_bpm=float(np.median(errors)), cases=cases)
    print(json.dumps(summary, indent=2))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
