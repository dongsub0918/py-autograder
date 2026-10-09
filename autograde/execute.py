"""Run a submission file into a namespace, the way "Run all" in Colab would.

The file is executed one top-level statement at a time in a single shared namespace.
Unlike Colab, a failing statement does not stop the run: it is recorded and skipped, and
later statements still run. Only values that were actually created end up in the namespace,
so anything depending on a failed statement is missing (and its tests fail on their own).
"""

import ast
import contextlib
import io
import json
import os
import pickle
import signal
from dataclasses import dataclass, field

STATEMENT_TIMEOUT = 10  # seconds per top-level statement


class StatementTimeout(Exception):
    pass


@dataclass
class Execution:
    namespace: dict
    statements: list = field(default_factory=list)  # top-level ast nodes that were run
    failures: list = field(default_factory=list)  # [{"line": int, "error": str}]
    from_ipynb: bool = False


def install_dataset_cache(cache_dir):
    """Make statsmodels' get_rdataset download each dataset once, then read it from disk."""
    try:
        import statsmodels.datasets as smd
    except ImportError:
        return
    original = smd.get_rdataset

    def cached_get_rdataset(dataname, package="datasets", cache=False):
        path = os.path.join(cache_dir, f"rdataset__{package}__{dataname}.pkl")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return pickle.load(f)
        result = original(dataname, package)
        os.makedirs(cache_dir, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            pickle.dump(result, f)
        os.replace(tmp, path)
        return result

    smd.get_rdataset = cached_get_rdataset


def notebook_to_source(source):
    """If the file is actually an .ipynb (JSON) renamed to .py, return its code cells joined
    as a script, dropping shell/magic lines (!pip, %matplotlib). Otherwise return None."""
    if not source.lstrip().startswith("{"):
        return None
    try:
        cells = json.loads(source)["cells"]
    except (ValueError, KeyError, TypeError):
        return None
    chunks = []
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        text = cell.get("source", "")
        text = "".join(text) if isinstance(text, list) else text
        chunks.append("\n".join(l for l in text.split("\n") if not l.lstrip().startswith(("!", "%"))))
    return "\n\n".join(chunks)


def parse_statements(source):
    """Return (statements, syntax_errors). Falls back to parsing blank-line-separated chunks
    (roughly one Colab cell each) when the whole file has a syntax error."""
    try:
        return ast.parse(source).body, []
    except SyntaxError:
        pass

    statements, errors = [], []
    lines = source.split("\n")
    start = 0
    for i in range(len(lines) + 1):
        at_boundary = i == len(lines) or (
            i > 0 and lines[i - 1].strip() == "" and lines[i][:1] not in ("", " ", "\t")
        )
        if not at_boundary or i == start:
            continue
        chunk = "\n".join(lines[start:i])
        try:
            tree = ast.parse(chunk)
            ast.increment_lineno(tree, start)
            statements.extend(tree.body)
        except SyntaxError as e:
            errors.append({"line": start + (e.lineno or 1), "error": f"SyntaxError: {e.msg}"})
        start = i
    return statements, errors


def _on_alarm(signum, frame):
    raise StatementTimeout(f"statement took longer than {STATEMENT_TIMEOUT}s")


def execute(path):
    """Run the file at `path` and return an Execution with the resulting namespace."""
    with open(path, encoding="utf-8", errors="replace") as f:
        source = f.read()

    converted = notebook_to_source(source)
    if converted is not None:
        source = converted

    statements, failures = parse_statements(source)
    namespace = {"__name__": "__main__", "__file__": str(path)}
    previous_handler = signal.signal(signal.SIGALRM, _on_alarm)

    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            for stmt in statements:
                code = compile(ast.Module(body=[stmt], type_ignores=[]), str(path), "exec")
                signal.alarm(STATEMENT_TIMEOUT)
                try:
                    exec(code, namespace)
                except (Exception, SystemExit, StatementTimeout) as e:
                    failures.append({"line": stmt.lineno, "error": f"{type(e).__name__}: {e}"})
                finally:
                    signal.alarm(0)
                sink.seek(0)
                sink.truncate()  # don't let student prints pile up in memory
    finally:
        signal.signal(signal.SIGALRM, previous_handler)

    return Execution(namespace, statements, failures, converted is not None)
