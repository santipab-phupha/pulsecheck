"""Audit displayed QRS errors after slope-based refinement."""
import json

import numpy as np

from audit_refined_rates import load_development_rates
from baseline import OUT, write_table
from compare_quality import TOLERANCE, load_csv


def load_slope_comparison():
    refined, peak = load_development_rates()
    slope = load_csv("slope-refinement.csv")
    assert [(r["id"], r["person"]) for r in slope] == [(r["id"], r["person"]) for r in refined]
    return slope, {r["id"]: r for r in refined}, peak


def error_group(row):
    if row["revised_outcome"] != "show_bad":
        return ""
    if row["previous_outcome"] == "show_good":
        return "new_in_slope"
    if row["peak_outcome"] == "show_good":
        return "remaining_from_nine"
    return "other_displayed_error"


def main():
    slope, refined, peak = load_slope_comparison()
    rows = []
    for row in slope:
        group = error_group(row)
        if not group:
            continue
        rec = row["id"]
        qrs, bpm = float(row["qrs_bpm"]), float(row["revised_bpm"])
        rates = [float(row["peak_bpm"]), float(refined[rec]["periodic_bpm"]), float(row["slope_bpm"])]
        closest = min(rates, key=lambda rate: abs(rate - qrs))
        score_margin = float(row["slope_score"]) - max(float(refined[rec]["prior_score"]),
                                                       float(refined[rec]["periodic_score"]))
        rows.append(dict(id=rec, person=row["person"], group=group, qrs_bpm=qrs,
                         peak_bpm=rates[0], periodic_bpm=rates[1], slope_bpm=rates[2],
                         previous_bpm=float(row["previous_bpm"]), current_bpm=bpm, signed_error=bpm-qrs,
                         used_slope=row["used_slope"] == "True", slope_score_margin=score_margin,
                         selected_estimate_within_5=abs(closest-qrs) <= TOLERANCE,
                         motion=peak[rec]["motion"], quality_annotation=peak[rec]["quality_annotation"]))
    old = [r for r in rows if r["group"] == "remaining_from_nine"]
    new = [r for r in rows if r["group"] == "new_in_slope"]
    assert (len(rows), len(old), len(new)) == (367, 7, 2)
    write_table("slope-error-audit.csv", rows)
    summary = dict(errors=len(rows), below_qrs=sum(r["signed_error"] < 0 for r in rows),
                   median_abs_error_bpm=float(np.median([abs(r["signed_error"]) for r in rows])),
                   rest=sum(r["motion"] == "0" for r in rows),
                   lower_quality_label=sum(r["quality_annotation"] == "0" for r in rows),
                   an_estimate_within_5=sum(r["selected_estimate_within_5"] for r in rows),
                   remaining_seven=old, new_two=new)
    (OUT / "slope-error-audit-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
