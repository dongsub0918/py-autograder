# py-autograder

Grades weekly Python discussion assignments (Colab notebooks downloaded as `.py`) and produces a
CSV that imports straight into the Canvas gradebook.

Each week has its own **pytest test file**. For every submission, the autograder runs the student's
file, then runs that week's tests against the variables the file left in memory. Passing tests are
added up into a score.

## Setup

Requires Python 3.11+ (developed on 3.12).

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`pandas` is pinned below 3.0 to match what Colab runs.

## Grading a week

1. Create a week folder, e.g. `discussion-2/`, containing:
   - `submissions/`: the files from Canvas (*Assignment → Download Submissions*), unzipped as is
   - `solution.py`: a correct, fully solved copy of the notebook
   - `test_discussion2.py`: the week's tests (see below)
2. From the project root, run:
   ```bash
   .venv/bin/python -m autograde discussion-2
   ```
3. Review `discussion-2/results/report.csv`.
4. Upload `discussion-2/results/canvas_import.csv` in Canvas: *Grades → Import*. Check the preview,
   then click *Save Changes*.

What the run does:

- **Anonymizes submissions.** Canvas names files `<name>[_LATE]_<canvas id>_<submission id>_<file>`.
  Each one is renamed to `<canvas id>.py`. If a student submitted more than once, only the newest
  file is kept and older ones are **deleted**.
- **Validates the tests.** The tests are run against `solution.py` first. If any test fails there,
  or the points don't add up, grading stops before any student is scored.
- **Grades each submission in sequence**, each in a fresh process.
- **Writes the results:**
  - `canvas_import.csv`: `Student,ID,SIS User ID,SIS Login ID,Section,<assignment>`. Only `ID`
    (the Canvas user ID) and the score are filled in. Canvas requires the other header columns
    but matches students by `ID` alone.
  - `report.csv`: one row per Canvas ID, with the score, `ok` / `FAIL: <reason>` for each test,
    and any statements in the student's file that raised errors.

To debug a single submission with full pytest output:

```bash
.venv/bin/pytest discussion-2/test_discussion2.py --submission discussion-2/submissions/123456.py
```

Add `-s` and put a `breakpoint()` in a test to inspect the student's variables interactively.

## Writing a week's test file

There must be exactly one `test_*.py` per week folder. It is an ordinary pytest file plus two
required constants:

```python
import numpy as np
from autograde import assert_matches, points

CANVAS_COLUMN = "Discussion Assignment 2 (3317196)"  # exact header from the Canvas gradebook
POINTS_POSSIBLE = 100                                # the @points values must add up to this

@points(50)
def test_ex1_seq(ns):
    assert_matches(ns.seq, np.arange(2, 28, 4))

@points(50)
def test_ex2_label(ns, src):
    assert ns.label == "x = 5"
    assert not src.hardcoded_fields("label"), "f-string must use variables"

@points(0)  # 0 points: shows up in report.csv as a flag, doesn't change the score
def test_ex1_uses_arange(src):
    assert "numpy.arange" in src.calls("seq")
```

### Fixtures

| Fixture | What it is |
|---|---|
| `ns` | The student's global variables after their file ran. `ns.foo` returns a deep copy of `foo`; if `foo` was never defined, the test fails with a clear message. |
| `src` | The student's code, for checking *how* something was computed (see `autograde/source.py`). |
| `exec_errors` | Statements that raised while running the file: `[{"line": ..., "error": ...}]`. |

`src` methods:

| Method | Example result |
|---|---|
| `src.code_of("x_fixed")` | `"np.arange(1, 6)"`: right-hand side of the last top-level assignment |
| `src.calls("x_fixed")` | `{"numpy.arange"}`: functions called, with import aliases resolved |
| `src.fstring_fields("both")` | `["x", "Y"]`: the code inside each `{...}`, or `None` if not an f-string |
| `src.hardcoded_fields("both")` | `["5", "17"]`: f-string fields that use no variable |

### Helpers and conventions

- `points(n)` sets how much a test is worth. Tests without it are worth 1.
- `assert_matches(actual, expected, rtol=1e-7)` compares numbers, arrays, lists and pandas columns
  by shape and value. A list and a numpy array with the same numbers match.
- A test passes or fails as a whole. If two requirements should be scored separately (e.g. the
  value and the method), write them as two tests.
- Tests should check exact variable names as given in the assignment.

## How it works

```
python -m autograde <week>            autograde/__main__.py  (orchestrator; never runs student code)
 ├─ anonymize submissions/
 ├─ pytest <test file> --submission solution.py      ─┐
 ├─ pytest <test file> --submission <id>.py           │ one fresh process per file;
 ├─ ...                                               │ results come back as a JSON file
 └─ write results/canvas_import.csv + report.csv     ─┘
```

Inside each pytest process (`autograde/plugin.py`):

1. `pytest_configure` registers `@points` and patches `statsmodels`' `get_rdataset` so datasets
   download once into `.cache/datasets/`.
2. During collection, it reads `CANVAS_COLUMN` / `POINTS_POSSIBLE` and checks that the points add up.
3. The `ns` / `src` fixtures run the submission once per process (`autograde/execute.py`):
   - Each top-level statement runs in a shared namespace, like Colab's *Run all*.
   - A statement that raises is recorded and skipped; later statements still run, so only the
     work that depends on it is lost.
   - Each statement has a 10 s timeout; `input()` fails immediately; student output is discarded.
   - A `.ipynb` renamed to `.py` is detected, and its code cells are graded.
4. Test outcomes are written to a JSON file that the orchestrator reads.

The student's code runs with a throwaway temporary directory as its working directory.

## Known limitations

- **Data files:** student code runs in a temporary directory, so `pd.read_csv("data.csv")` with a
  relative path will fail. A week that ships data files needs them copied into that directory
  (in `run_tests()` in `autograde/__main__.py`).
- **Datasets loaded other ways:** only `statsmodels.datasets.get_rdataset` is cached. Other ways of
  loading datasets (`pd.read_csv(url)`, `seaborn.load_dataset`) hit the network for every
  submission until a similar patch is added in `autograde/execute.py`.
- **Not a security sandbox:** submissions run as your user, with your file and network access.
  Process isolation protects against crashes and infinite loops, not malicious code.
- **Unix only:** per-statement timeouts use `SIGALRM` (macOS/Linux).

## Privacy

Student data stays out of git (see `.gitignore`): `submissions/`, `results/`, `solution.py`, and
any Canvas gradebook exports. Submissions are renamed to Canvas IDs before grading, and outputs
contain only Canvas IDs and scores. Students' own code can still contain identifying information
(e.g. a name in a comment).
