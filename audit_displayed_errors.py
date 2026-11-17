"""Audit the 411 displayed errors in the QRS-trained peak selector."""
import json
import zipfile
from collections import Counter

import numpy as np

from baseline import OUT, ROOT, read_wave, write_table
from compare_quality import TOLERANCE, load_csv
from peak_selection import peak_candidates


def development_rows():
    rows = load_csv("peak-selection-qrs.csv")
    development = [r for r in load_csv("fingertip-manifest.csv") if r["split"] == "development"]
    assert [(r["id"], r["person"]) for r in rows] == [(r["id"], r["person"]) for r in development]
    return rows


def main():
    dev = development_rows()
    shown = [r for r in dev if r["candidate"].startswith("show_")]
    missed = [r for r in shown if abs(float(r["candidate_bpm"]) - float(r["qrs_bpm"])) > TOLERANCE]
    assert len(missed) == 411
    rows = []
    with zipfile.ZipFile(ROOT / "data/butppg-2.0.0.zip") as archive:
        prefix = next(name.rsplit("/", 1)[0] + "/" for name in archive.namelist()
                      if name.endswith("/subject-info.csv"))
        for r in missed:
            waves, fs = read_wave(archive, prefix, r["id"], "PPG", all_ppg_channels=True)
            candidates = peak_candidates(waves, fs)
            selected_bpm, _, _, features = next(c for c in candidates
                                                if "RGB"[c[1]] == r["channel"] and c[2] == int(r["polarity"]))
            assert np.isclose(selected_bpm, float(r["candidate_bpm"]))
            qrs_bpm = float(r["qrs_bpm"])
            # Feature 3 is the 10-second count expressed in bpm minus the interval estimate.
            peak_count = round((features[3] + selected_bpm) / 6)
            closest_bpm = min((bpm for bpm, _, _, _ in candidates), key=lambda bpm: abs(bpm - qrs_bpm))
            rows.append(dict(id=r["id"], person=r["person"], motion=r["motion"],
                             quality_annotation=r["quality_annotation"], channel=r["channel"],
                             selected_bpm=selected_bpm, qrs_bpm=qrs_bpm, signed_error=selected_bpm - qrs_bpm,
                             selected_peaks=peak_count, qrs_count=int(r["ecg_beats"]),
                             closest_original_candidate_bpm=closest_bpm,
                             original_candidate_within_5=abs(closest_bpm - qrs_bpm) <= TOLERANCE))
    write_table("displayed-error-audit.csv", rows)
    error = np.array([r["signed_error"] for r in rows])
    diff = np.array([r["selected_peaks"] - r["qrs_count"] for r in rows])
    report = dict(displayed_errors=len(rows), displayed_windows=len(shown),
                  below_qrs=int(sum(error < 0)), above_qrs=int(sum(error > 0)),
                  median_error_bpm=float(np.median(abs(error))),
                  fewer_peaks=int(sum(diff < 0)), equal_peaks=int(sum(diff == 0)), more_peaks=int(sum(diff > 0)),
                  at_rest=sum(r["motion"] == "0" for r in rows),
                  displayed_at_rest=sum(r["motion"] == "0" for r in shown),
                  labeled_low_quality=sum(r["quality_annotation"] == "0" for r in rows),
                  other_candidate_within_5=sum(r["original_candidate_within_5"] for r in rows),
                  errors_by_person=dict(Counter(r["person"] for r in rows)))
    text = json.dumps(report, indent=2)
    (OUT / "displayed-error-audit-summary.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
