"""Grade one week's submissions against that week's test file.

Usage:
    .venv/bin/python -m autograde discussion-1

The week folder must contain:
    test_*.py      exactly one test file (defines CANVAS_COLUMN and POINTS_POSSIBLE)
    solution.py    a correct submission; it must pass every test before grading starts
    submissions/   files as downloaded from Canvas

Steps:
    1. Anonymize submissions: Canvas names them <name>[_LATE]_<canvas id>_<submission id>_<file>;
       each becomes <canvas id>.py. If a student submitted several times, only the newest is
       kept and the older files are deleted.
    2. Run the tests against solution.py; stop unless every test passes.
    3. For each submission, one at a time, run pytest in a fresh process.
    4. Write <week>/results/canvas_import.csv (upload via Grades -> Import) and report.csv.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBMISSION_TIMEOUT = 180  # seconds for one submission's whole test run
CANVAS_NAME = re.compile(
    r"^(?P<slug>[^_]+)(?:_LATE)?_(?P<canvas_id>\d+)_(?P<submission_id>\d+)_.*\.(py|ipynb)$", re.I)
ANONYMIZED_NAME = re.compile(r"^\d+\.py$")
# Canvas rejects the file unless these identity columns are present; only ID needs a value.
IDENTITY_COLUMNS = ["Student", "ID", "SIS User ID", "SIS Login ID", "Section"]


def anonymize_submissions(folder):
    """Rename Canvas-named files to <canvas id>.py, keeping only the newest per student.
    Returns names of files left alone because they aren't recognizable submissions."""
    newest, unrecognized = {}, []
    for path in sorted(folder.iterdir()):
        if path.name.startswith(".") or ANONYMIZED_NAME.match(path.name):
            continue
        m = CANVAS_NAME.match(path.name)
        if not m:
            unrecognized.append(path.name)
            continue
        cid, sid = m["canvas_id"], int(m["submission_id"])
        if cid in newest and newest[cid][0] > sid:
            path.unlink()
            continue
        if cid in newest:
            newest[cid][1].unlink()
        newest[cid] = (sid, path)
    for cid, (_, path) in newest.items():
        path.replace(folder / f"{cid}.py")  # a fresh download replaces an earlier <id>.py
    if newest:
        print(f"Anonymized {len(newest)} submissions to <canvas id>.py")
    return unrecognized


def run_tests(test_file, submission):
    """Run the week's tests against one submission in a fresh pytest process."""
    with tempfile.TemporaryDirectory(prefix="autograde-") as tmp:
        out = Path(tmp) / "results.json"
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file),
                 "-p", "autograde.plugin", "-p", "no:cacheprovider", "-q",
                 "--submission", str(submission), "--results-json", str(out),
                 "--rootdir", str(ROOT)],
                cwd=tmp,  # anything the student writes to disk lands here and is discarded
                env={**os.environ, "PYTHONPATH": str(ROOT), "MPLBACKEND": "Agg"},
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, timeout=SUBMISSION_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {"crash": f"test run timed out after {SUBMISSION_TIMEOUT}s"}
        if not out.exists():
            output = proc.stdout.strip()[-2000:]
            return {"crash": f"test process ended without results (exit code {proc.returncode})"
                             + (f": {output}" if output else "")}
        return json.loads(out.read_text())


def score_of(result):
    return sum(t["points"] for t in result["tests"] if t["passed"])


def format_score(x):
    x = round(x, 2)
    return str(int(x)) if x == int(x) else f"{x:.2f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("week", help="week folder, e.g. discussion-1")
    week = Path(parser.parse_args().week).resolve()

    test_files = sorted(week.glob("test_*.py"))
    if len(test_files) != 1:
        sys.exit(f"Expected exactly one test_*.py in {week}, found {len(test_files)}")
    test_file = test_files[0]

    unrecognized = anonymize_submissions(week / "submissions")

    print(f"Checking {test_file.name} against solution.py ...")
    key = run_tests(test_file, week / "solution.py")
    if "crash" in key:
        sys.exit(f"Test run failed on solution.py:\n{key['crash']}")
    failing = [t for t in key["tests"] if not t["passed"]]
    if failing or key["exec_errors"]:
        print("solution.py does not pass cleanly — fix the solution or the tests first:")
        for e in key["exec_errors"]:
            print(f"  line {e['line']}: {e['error']}")
        for t in failing:
            print(f"  {t['name']}: {t['message']}")
        sys.exit(1)
    column, test_names = key["canvas_column"], [t["name"] for t in key["tests"]]

    submissions = sorted((p for p in (week / "submissions").iterdir() if ANONYMIZED_NAME.match(p.name)),
                         key=lambda p: int(p.stem))
    rows, scores, fail_counts = [], [], Counter()
    for i, path in enumerate(submissions, 1):
        print(f"\r[{i}/{len(submissions)}] {path.name:<14}", end="", flush=True)
        result = run_tests(test_file, path)
        cid = path.stem
        if "crash" in result:
            rows.append({"ID": cid, "Score": "0", "Notes": "test run crashed: "
                         + " ".join(result["crash"].split())[-300:]})
            scores.append(0)
            continue
        score = score_of(result)
        scores.append(score)
        outcomes = {t["name"]: "ok" if t["passed"] else f"FAIL: {t['message']}" for t in result["tests"]}
        fail_counts.update(t["name"] for t in result["tests"] if not t["passed"])
        notes = ["file was an .ipynb renamed to .py; graded its code cells"] if result["from_ipynb"] else []
        notes += [f"line {e['line']}: {e['error']}" for e in result["exec_errors"]]
        rows.append({"ID": cid, "Score": format_score(score), **outcomes, "Notes": " | ".join(notes)})
    print()

    out_dir = week / "results"
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "canvas_import.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(IDENTITY_COLUMNS + [column])
        for row in rows:
            writer.writerow(["", row["ID"], "", "", "", row["Score"]])
    with open(out_dir / "report.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ID", "Score", *test_names, "Notes"], restval="")
        writer.writeheader()
        writer.writerows(rows)

    possible = key["points_possible"]
    print(f"\n{column}: graded {len(scores)} submissions, out of {format_score(possible)}")
    if scores:
        mean = sum(scores) / len(scores)
        full = sum(1 for s in scores if abs(s - possible) < 1e-6)
        print(f"Mean {mean:.1f}   full marks {full}   zero {sum(1 for s in scores if s == 0)}")
    if fail_counts:
        print("Failed tests: " + ", ".join(f"{n} ({c})" for n, c in fail_counts.most_common()))
    for name in unrecognized:
        print(f"WARNING: not graded, unrecognized file name: submissions/{name}")
    print(f"\nWrote {out_dir / 'canvas_import.csv'}\n      {out_dir / 'report.csv'}")


if __name__ == "__main__":
    main()
