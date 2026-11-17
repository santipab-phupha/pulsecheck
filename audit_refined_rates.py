"""Inspect the displayed errors after the first periodicity refinement."""
import json
from collections import Counter

import numpy as np

from audit_displayed_errors import development_rows
from baseline import OUT, write_table
from compare_quality import TOLERANCE, load_csv


def load_development_rates():
    refined = load_csv("refined-rates.csv")
    prior = development_rows()
    assert [(r["id"], r["person"]) for r in refined] == [(r["id"], r["person"]) for r in prior]
    return refined, {r["id"]: r for r in prior}


def main():
    refined, prior = load_development_rates()
    peak_audit = {r["id"]: r for r in load_csv("displayed-error-audit.csv")}
    misses = [r for r in refined if r["refined_outcome"] == "show_bad"]
    rows = []
    for row in misses:
        record = row["id"]
        qrs = float(row["qrs_bpm"])
        peak = float(row["prior_bpm"])
        periodic = float(row["periodic_bpm"])
        value = float(row["refined_bpm"])
        peak_good = abs(peak - qrs) <= TOLERANCE
        periodic_good = abs(periodic - qrs) <= TOLERANCE
        alternative_good = peak_good or peak_audit[record]["original_candidate_within_5"] == "True"
        method = ("weighted_mean" if abs(peak - periodic) <= 3 else
                  "periodic" if float(row["periodic_score"]) > float(row["prior_score"]) else "peak")
        rows.append(dict(id=record, person=row["person"], qrs_bpm=qrs, peak_bpm=peak, periodic_bpm=periodic,
                         refined_bpm=value, signed_error_bpm=value - qrs,
                         decision=method, peak_score=row["prior_score"], periodic_score=row["periodic_score"],
                         peak_within_5=peak_good, periodic_within_5=periodic_good,
                         any_peak_within_5=alternative_good,
                         motion=prior[record]["motion"], quality_annotation=prior[record]["quality_annotation"]))

    regressions = [r for r in rows if r["peak_within_5"]]
    assert len(rows) == 375 and len(regressions) == 9
    write_table("refined-error-audit.csv", rows)
    report = dict(total=len(rows), below_qrs=sum(r["signed_error_bpm"] < 0 for r in rows),
                  median_abs_error_bpm=float(np.median([abs(r["signed_error_bpm"]) for r in rows])),
                  rest=sum(r["motion"] == "0" for r in rows),
                  lower_quality_label=sum(r["quality_annotation"] == "0" for r in rows),
                  estimates_within_3=sum(abs(r["peak_bpm"] - r["periodic_bpm"]) <= 3 for r in rows),
                  periodic_candidate_within_5=sum(r["periodic_within_5"] for r in rows),
                  any_candidate_within_5=sum(r["any_peak_within_5"] or r["periodic_within_5"] for r in rows),
                  regressions_by_decision=dict(Counter(r["decision"] for r in regressions)),
                  regressions=regressions)
    text = json.dumps(report, indent=2)
    (OUT / "refined-error-audit-summary.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
