"""Freeze PulseCheck on development recordings, then score the locked pair on held-out people."""
import argparse
import hashlib
import json
import pickle
import platform
import zipfile
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version

import numpy as np
from threadpoolctl import threadpool_limits

from adaptive_peaks import counts, outcome
from baseline import OUT, ROOT, read_wave, write_table
from compare_quality import TOLERANCE, load_csv
from peak_selection import best_candidates, grouped_validation_scores, peak_candidates, train_model
from reference_audit import qrs_rate
from refine_displayed_rate import AGREEMENT_BPM, fit_rate_model, predict_rates, rate_features, refine
from refine_with_spectral_checks import (
    DISTANT_PEAK_SUPPORT_MARGIN,
    MINIMUM_SLOPE_SUPPORT,
    NEAR_PEAK_SUPPORT_MARGIN,
    verify_rate,
)
from refine_with_waveform_slopes import select_rate, slope_features

ARCHIVE = ROOT / "data" / "butppg-2.0.0.zip"
MODEL_PATH = ROOT / "data" / "final-holdout-models.pkl"
LOCK_PATH = OUT / "final-holdout-lock.json"
RETRY_QUANTILE = 0.23
SOURCE_FILES = (
    "final_holdout.py", "baseline.py", "adaptive_peaks.py", "compare_quality.py",
    "peak_selection.py", "reference_audit.py", "refine_displayed_rate.py",
    "refine_with_waveform_slopes.py", "refine_with_spectral_checks.py", "requirements.txt",
    "results/fingertip-manifest.csv", "demo/dist/data.js",
)


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def read_split():
    all_rows = load_csv("fingertip-manifest.csv")
    development = [r for r in all_rows if r["split"] == "development"]
    holdout = [r for r in all_rows if r["split"] == "holdout"]
    if len(all_rows) != 1926 or len({r["id"] for r in all_rows}) != len(all_rows):
        raise ValueError("Unexpected number of unique records in the original split")
    dev_people = {r["person"] for r in development}
    held_people = {r["person"] for r in holdout}
    if (len(development), len(holdout), len(dev_people), len(held_people)) != (1540, 386, 24, 6):
        raise ValueError("The original 24/6 participant split is required")
    if dev_people & held_people or any(r["id"][:3] != r["person"] for r in all_rows):
        raise ValueError("Unexpected participant mapping in the split")
    return development, holdout


def archive_prefix(archive):
    return next(name.rsplit("/", 1)[0] + "/" for name in archive.namelist() if name.endswith("/subject-info.csv"))


def qrs_reference(archive, prefix, record):
    return qrs_rate(archive.read(f"{prefix}{record}/{record}.qrs"))


def source_hashes():
    return {name: digest(ROOT / name) for name in SOURCE_FILES}


def runtime_versions():
    return {"python": platform.python_version(), **{
        name: version(name) for name in ("numpy", "scipy", "scikit-learn", "threadpoolctl")
    }}


def freeze():
    if LOCK_PATH.exists() or (OUT / "final-holdout-summary.json").exists():
        raise FileExistsError(f"The evaluation is already locked in {LOCK_PATH}")
    development, holdout = read_split()
    print(f"Training only on {len(development)} development windows.", flush=True)
    candidate_features, candidate_labels, windows = [], [], []
    grid, slope_grid, references = [], [], []
    with zipfile.ZipFile(ARCHIVE) as archive:
        prefix = archive_prefix(archive)
        for i, row in enumerate(development):
            record = row["id"]
            waves, fs = read_wave(archive, prefix, record, "PPG", all_ppg_channels=True)
            ref = qrs_reference(archive, prefix, record)
            features = rate_features(waves, fs)
            for rate, _, _, values in peak_candidates(waves, fs):
                candidate_features.append(values)
                candidate_labels.append(abs(rate - ref) <= TOLERANCE)
                windows.append(i)
            grid.append(features)
            slope_grid.append(np.column_stack([features, slope_features(waves, fs)]))
            references.append(ref)
    windows = np.array(windows)
    people = np.array([r["person"] for r in development])
    x = np.array(candidate_features)
    y = np.array(candidate_labels)
    references = np.array(references)
    with threadpool_limits(limits=1):
        scores = grouped_validation_scores(x, y, windows, people[windows])
        cutoff = float(np.quantile(scores, RETRY_QUANTILE))
        models = dict(peak=train_model(x, y), periodic=fit_rate_model(np.array(grid), references),
                      slope=fit_rate_model(np.array(slope_grid), references, max_iter=65),
                      quality_cutoff=cutoff)
    data = pickle.dumps(models, protocol=pickle.HIGHEST_PROTOCOL)
    lock = dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
                versions=runtime_versions(), source_sha256=source_hashes(), archive_sha256=digest(ARCHIVE),
                models_sha256=hashlib.sha256(data).hexdigest(),
                development=dict(records=len(development), people=sorted(set(people.tolist()))),
                holdout=dict(records=len(holdout), people=sorted({r["person"] for r in holdout})),
                models={key: models[key].get_params() for key in ("peak", "periodic", "slope")},
                quality_gate=dict(dev_group_folds=4, target_quantile=RETRY_QUANTILE,
                                  validation_window_count=len(scores), cutoff=cutoff),
                spectral_gate=dict(min_slope_support=MINIMUM_SLOPE_SUPPORT,
                                   near_peak_support=NEAR_PEAK_SUPPORT_MARGIN,
                                   distant_peak_support=DISTANT_PEAK_SUPPORT_MARGIN,
                                   near_bpm=AGREEMENT_BPM, distant_bpm=2 * TOLERANCE),
                comparison=dict(previous="Waveform slope refinement",
                                latest="Spectral checks (selected Chrome demo version)",
                                reference="Median instantaneous bpm from same-window annotated ECG QRS intervals",
                                tolerance_bpm=TOLERANCE))
    MODEL_PATH.write_bytes(data)
    with LOCK_PATH.open("x", encoding="utf-8") as file:
        json.dump(lock, file, indent=2)
        file.write("\n")
    print(f"Frozen quality cutoff {cutoff:.8f}; bundle SHA-256 {lock['models_sha256']}")


def predict(waves, fs, models):
    candidates = peak_candidates(waves, fs)
    if not candidates:
        return None, None, None, True, "missing_peaks"
    selected, confidence = best_candidates(models["peak"], np.array([c[3] for c in candidates]),
                                            np.zeros(len(candidates), dtype=int))[0]
    peak = candidates[selected][0]
    if confidence < models["quality_cutoff"]:
        return peak, peak, confidence, True, "retry"
    features = rate_features(waves, fs)
    periodic, periodic_scores = predict_rates(models["periodic"], features[None, :, :])
    slope, slope_scores = predict_rates(models["slope"], np.column_stack([
        features, slope_features(waves, fs)
    ])[None, :, :])
    periodic_rate, slope_rate = float(periodic[0]), float(slope[0])
    periodic_score, slope_score = float(periodic_scores[0]), float(slope_scores[0])
    previous, used = select_rate(peak, periodic_rate, confidence, periodic_score, slope_rate, slope_score)
    pre_slope = refine(peak, confidence, periodic_rate, periodic_score)
    latest, decision, _ = verify_rate(waves, fs, dict(peak_bpm=peak, slope_bpm=slope_rate,
                                                    revised_bpm=previous, previous_bpm=pre_slope,
                                                    used_slope=str(used)), dict(periodic_bpm=periodic_rate))
    return float(previous), float(latest), float(confidence), False, decision


def summarize(rows):
    totals = {variant: counts([r[f"{variant}_outcome"] for r in rows]) for variant in ("previous", "latest")}
    return dict(counts=totals, per_100={variant: {
                    **{kind: total * 100 / len(rows) for kind, total in group.items()},
                    "retry_total": sum(group[k] for k in ("retry_bad", "retry_good", "missing")) * 100 / len(rows),
                } for variant, group in totals.items()})


def evaluate():
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    data = MODEL_PATH.read_bytes()
    if (source_hashes() != lock["source_sha256"] or digest(ARCHIVE) != lock["archive_sha256"]
            or hashlib.sha256(data).hexdigest() != lock["models_sha256"] or runtime_versions() != lock["versions"]):
        raise ValueError("The frozen code, data, model bundle, or runtime changed")
    models = pickle.loads(data)
    if models["quality_cutoff"] != lock["quality_gate"]["cutoff"]:
        raise ValueError("The frozen quality cutoff does not match the bundle")
    _, holdout = read_split()
    rows = []
    with zipfile.ZipFile(ARCHIVE) as archive, threadpool_limits(limits=1):
        prefix = archive_prefix(archive)
        for row in holdout:
            record = row["id"]
            waves, fs = read_wave(archive, prefix, record, "PPG", all_ppg_channels=True)
            previous, latest, confidence, retry, decision = predict(waves, fs, models)
            rows.append(dict(id=record, person=row["person"], previous_bpm=previous, latest_bpm=latest,
                             peak_score=confidence, retry=retry, spectral_decision=decision))
        write_table("final-holdout-predictions.csv", rows)
        for row in rows:
            ref = qrs_reference(archive, prefix, row["id"])
            row.update(qrs_bpm=ref, previous_outcome=outcome(row["previous_bpm"], ref, row["retry"]),
                       latest_outcome=outcome(row["latest_bpm"], ref, row["retry"]))
    write_table("final-holdout-comparison.csv", rows)
    transitions = Counter(f"{r['previous_outcome']} to {r['latest_outcome']}" for r in rows)
    participants = sorted({r["person"] for r in rows})
    report = dict(records=len(rows), people=len(participants), frozen_models_sha256=lock["models_sha256"],
                  **summarize(rows), transitions=transitions,
                  per_person={p: summarize([r for r in rows if r["person"] == p]) for p in participants})
    text = json.dumps(report, indent=2)
    (OUT / "final-holdout-summary.json").write_text(text + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("records", "people", "counts", "per_100", "transitions")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "evaluate"))
    stage = parser.parse_args().stage
    {"freeze": freeze, "evaluate": evaluate}[stage]()
