"""Rebuild and score the locked protocol in a fresh directory."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from final_holdout import ARCHIVE, ROOT, SOURCE_FILES, digest, runtime_versions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE, help="Path to the BUT PPG 2.0.0 ZIP")
    parser.add_argument("--output", type=Path, default=ROOT / "reproduction", help="New directory for the rerun")
    args = parser.parse_args()

    published_lock = json.loads((ROOT / "results/final-holdout-lock.json").read_text(encoding="utf-8"))
    if not args.archive.is_file():
        parser.error(f"Dataset archive not found at {args.archive}. See the README for the download.")
    if digest(args.archive) != published_lock["archive_sha256"]:
        parser.error("Dataset archive does not match the published SHA-256.")
    if args.output.exists():
        parser.error(f"Output already exists at {args.output}. Choose a new directory.")
    if runtime_versions() != published_lock["versions"]:
        parser.error(f"Use the recorded runtime for this rerun: {published_lock['versions']}")

    # Recreate the file layout expected by the original frozen entry point.
    args.output.mkdir(parents=True)
    for source in ROOT.glob("*.py"):
        if source.name != Path(__file__).name:
            shutil.copyfile(source, args.output / source.name)
    for name, source in {
        "requirements.txt": ROOT / "requirements.txt",
        "data/butppg-2.0.0.zip": args.archive,
        "results/fingertip-manifest.csv": ROOT / "results/fingertip-manifest.csv",
        "demo/dist/data.js": ROOT / "demo/assets/recordings.js",
    }.items():
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    reproduced_hashes = {name: digest(args.output / name) for name in SOURCE_FILES}
    if reproduced_hashes != published_lock["source_sha256"]:
        parser.error("Source hashes differ from the original lock. Check Git line-ending conversion.")

    for stage in ("freeze", "evaluate"):
        subprocess.run([sys.executable, "final_holdout.py", stage], cwd=args.output, check=True)

    summary_path = Path("results/final-holdout-summary.json")
    published = json.loads((ROOT / summary_path).read_text(encoding="utf-8"))
    reproduced = json.loads((args.output / summary_path).read_text(encoding="utf-8"))
    fields = ("records", "people", "counts", "transitions", "per_person")
    differences = [field for field in fields if reproduced[field] != published[field]]
    if differences:
        raise SystemExit(f"Rerun differs from the published results in {', '.join(differences)}. See {args.output}.")
    print(f"The published counts and transitions were reproduced. See {args.output / summary_path}.")


if __name__ == "__main__":
    main()
