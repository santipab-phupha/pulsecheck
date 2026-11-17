"""Export two development-only BUT PPG windows for the static demo."""
import csv
import json
import zipfile

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt

from baseline import OUT, ROOT, read_wave
from reference_audit import qrs_times

CASES = {"135021": "show_good", "136096": "show_bad"}
DEMO_DATA = ROOT / "demo" / "dist" / "data.js"
DEMO_ASSET = ROOT / "demo" / "assets" / "recordings.js"


def read_demo_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {r["id"]: r for r in csv.DictReader(source) if r["id"] in CASES}


def normalize(trace):
    centered = trace - np.median(trace)
    return np.round(centered / np.max(np.abs(centered)), 6).tolist()


def export():
    manifest = read_demo_rows(OUT / "fingertip-manifest.csv")
    results = read_demo_rows(OUT / "spectral-refinement.csv")
    for record, outcome in CASES.items():
        if manifest[record]["split"] != "development":
            raise ValueError(f"{record} is outside the development split")
        row = results[record]
        if (row["person"] != manifest[record]["person"] or row["previous_outcome"] != "show_bad"
                or row["revised_outcome"] != outcome):
            raise ValueError(f"{record} no longer matches the demo comparison")

    cases = []
    with zipfile.ZipFile(ROOT / "data" / "butppg-2.0.0.zip") as archive:
        prefix = next(name.rsplit("/", 1)[0] + "/" for name in archive.namelist()
                      if name.endswith("/subject-info.csv"))
        for record in CASES:
            ppg, ppg_fs = read_wave(archive, prefix, record, "PPG")
            ecg, ecg_fs = read_wave(archive, prefix, record, "ECG")
            if ecg_fs != 1000:
                raise ValueError(f"Unexpected ECG sample rate for {record}: {ecg_fs}")
            ppg = sosfiltfilt(butter(3, [0.55, 4.7], fs=ppg_fs, btype="bandpass", output="sos"), ppg)
            ecg = sosfiltfilt(butter(2, 0.5, fs=ecg_fs, btype="highpass", output="sos"), ecg)
            beats = qrs_times(archive.read(f"{prefix}{record}/{record}.qrs")) / ecg_fs
            ecg_bpm = float(results[record]["qrs_bpm"])
            if beats[-1] >= 10 or not np.isclose(np.median(60 / np.diff(beats)), ecg_bpm):
                raise ValueError(f"ECG annotations do not match the reference for {record}")
            cases.append(dict(
                id=record,
                previousBpm=float(results[record]["previous_bpm"]),
                latestBpm=float(results[record]["revised_bpm"]),
                ecgBpm=ecg_bpm,
                ppg=normalize(ppg),
                ppgHz=ppg_fs,
                ecg=normalize(resample_poly(ecg, 1, 5)),
                ecgHz=ecg_fs // 5,
                beats=np.round(beats, 3).tolist(),
            ))
    payload = json.dumps({"cases": cases}, separators=(",", ":"), allow_nan=False)
    for destination in (DEMO_ASSET, DEMO_DATA):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(f"window.PULSECHECK_DATA = {payload};\n", encoding="utf-8")
    print(f"Exported {len(cases)} development recordings to {DEMO_DATA}")


if __name__ == "__main__":
    export()
