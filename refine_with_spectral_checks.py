"""Test waveform checks on the 24 development participants."""
import json
import zipfile
from collections import Counter

import numpy as np
from scipy.signal import butter, sosfiltfilt

from adaptive_peaks import counts, outcome
from audit_slope_errors import error_group, load_slope_comparison
from baseline import OUT, ROOT, read_wave, write_table
from compare_quality import TOLERANCE
from refine_displayed_rate import AGREEMENT_BPM, spectral_support

MINIMUM_SLOPE_SUPPORT = 0.50
NEAR_PEAK_SUPPORT_MARGIN = 1.15
DISTANT_PEAK_SUPPORT_MARGIN = 1.50


def verify_rate(waves, fs, row, earlier):
    peak = float(row["peak_bpm"])
    periodic = float(earlier["periodic_bpm"])
    slope = float(row["slope_bpm"])
    pulse = sosfiltfilt(butter(3, [0.55, 4.7], fs=fs, btype="bandpass", output="sos"), waves, axis=0)
    power = spectral_support(pulse, fs, (1,), rates=(peak, periodic, slope))[0]
    peak_power, periodic_power, slope_power = power.max(axis=1)
    revised = float(row["revised_bpm"])
    decision = "kept"
    if row["used_slope"] == "True" and slope_power < MINIMUM_SLOPE_SUPPORT * max(peak_power, periodic_power):
        revised = float(row["previous_bpm"])
        decision = "restored_before_slope"
    gap = abs(peak - revised)
    alternative_power = max(periodic_power, slope_power)
    agrees = gap <= AGREEMENT_BPM and peak_power > NEAR_PEAK_SUPPORT_MARGIN * alternative_power
    strong_support = gap <= 2 * TOLERANCE and peak_power > DISTANT_PEAK_SUPPORT_MARGIN * alternative_power
    if agrees or strong_support:
        revised = (peak + revised) / 2
        decision = "averaged_with_supported_peak"
    return revised, decision, tuple(map(float, (peak_power, periodic_power, slope_power)))


def main():
    source, earlier, _ = load_slope_comparison()
    rows = []
    with zipfile.ZipFile(ROOT / "data/butppg-2.0.0.zip") as archive:
        prefix = next(name.rsplit("/", 1)[0] + "/" for name in archive.namelist()
                      if name.endswith("/subject-info.csv"))
        for row in source:
            record = row["id"]
            old = float(row["revised_bpm"])
            ref = float(row["qrs_bpm"])
            retry = row["revised_outcome"].startswith("retry_")
            if retry:
                revised, decision, power = old, "retry", (None, None, None)
            else:
                waves, fs = read_wave(archive, prefix, record, "PPG", all_ppg_channels=True)
                revised, decision, power = verify_rate(waves, fs, row, earlier[record])
            rows.append(dict(id=record, person=row["person"], previous_error_group=error_group(row),
                             qrs_bpm=ref, previous_bpm=old, revised_bpm=revised, decision=decision,
                             peak_power=power[0], periodic_power=power[1], slope_power=power[2],
                             previous_outcome=row["revised_outcome"], revised_outcome=outcome(revised, ref, retry)))
    previous = counts([r["previous_outcome"] for r in rows])
    revised = counts([r["revised_outcome"] for r in rows])
    assert previous == dict(show_bad=367, show_good=791, retry_bad=310, retry_good=72, missing=0)
    assert (previous["retry_good"], previous["retry_bad"]) == (revised["retry_good"], revised["retry_bad"])
    fixed = [r for r in rows if r["previous_outcome"] == "show_bad" and r["revised_outcome"] == "show_good"]
    new_errors = [r for r in rows if r["previous_outcome"] == "show_good" and r["revised_outcome"] == "show_bad"]
    focused = [r for r in rows if r["previous_error_group"] in {"remaining_from_nine", "new_in_slope"}]
    report = dict(attempts=len(rows), people=len({r["person"] for r in rows}),
                  previous=previous, revised=revised,
                  displayed_errors_fixed=fixed, new_displayed_errors=new_errors,
                  focused_cases=focused, decisions=dict(Counter(r["decision"] for r in rows)),
                  per_100={name: {key: value * 100 / len(rows) for key, value in totals.items()}
                           for name, totals in [("previous", previous), ("revised", revised)]})
    write_table("spectral-refinement.csv", rows)
    (OUT / "spectral-refinement-summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Displayed errors: {previous['show_bad']} to {revised['show_bad']}; "
          f"fixed {len(fixed)}, newly wrong {len(new_errors)}")


if __name__ == "__main__":
    main()
