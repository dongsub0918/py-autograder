"""pytest plugin: runs one submission, exposes its namespace to the tests, records results.

Registered by the repo-root conftest.py. A week's test file must define:

    CANVAS_COLUMN = "Discussion Assignment 1 (3304388)"   # exact Canvas gradebook header
    POINTS_POSSIBLE = 100                                 # @points values must add up to this

Run a single submission by hand (full assertion output):

    .venv/bin/pytest discussion-1/test_discussion1.py --submission discussion-1/submissions/779727.py
"""

import copy
import json
from pathlib import Path

import pytest

from autograde.execute import execute, install_dataset_cache
from autograde.source import Source

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "datasets"
DEFAULT_POINTS = 1

_meta_key = pytest.StashKey[dict]()
_results_key = pytest.StashKey[dict]()
_execution_key = pytest.StashKey[object]()


class Namespace:
    """Read-only view of a submission's globals. `ns.both` returns a deep copy of the student's
    `both`, so tests can't affect each other; an undefined name fails the test cleanly."""

    def __init__(self, values):
        object.__setattr__(self, "_values", values)

    def __getattr__(self, name):
        if name not in self._values:
            pytest.fail(f"variable `{name}` was never defined", pytrace=False)
        value = self._values[name]
        try:
            return copy.deepcopy(value)
        except Exception:
            return value

    def __setattr__(self, name, value):
        raise AttributeError("ns is read-only")

    def __contains__(self, name):
        return name in self._values


def pytest_addoption(parser):
    group = parser.getgroup("autograde")
    group.addoption("--submission", help="student .py file to run before the tests")
    group.addoption("--results-json", help="write per-test outcomes to this JSON file")


def pytest_configure(config):
    config.addinivalue_line("markers", "points(n): points this test is worth")
    config.stash[_results_key] = {}
    install_dataset_cache(str(CACHE_DIR))


def _points(item):
    marker = item.get_closest_marker("points")
    return marker.args[0] if marker else DEFAULT_POINTS


def pytest_collection_modifyitems(session, config, items):
    modules = {item.module for item in items}
    if len(modules) != 1:
        raise pytest.UsageError("autograde expects exactly one week's test file per run")
    module = modules.pop()
    for name in ("CANVAS_COLUMN", "POINTS_POSSIBLE"):
        if not hasattr(module, name):
            raise pytest.UsageError(f"{module.__file__} must define {name}")
    total = sum(_points(item) for item in items)
    if abs(total - module.POINTS_POSSIBLE) > 1e-6:
        raise pytest.UsageError(
            f"@points add up to {total:g}, but POINTS_POSSIBLE = {module.POINTS_POSSIBLE:g}")
    config.stash[_meta_key] = {
        "canvas_column": module.CANVAS_COLUMN,
        "points_possible": module.POINTS_POSSIBLE,
        "tests": [{"name": item.name, "points": _points(item)} for item in items],
    }


def _execution(config):
    if _execution_key not in config.stash:
        path = config.getoption("--submission")
        if not path:
            pytest.fail("no --submission given", pytrace=False)
        config.stash[_execution_key] = execute(Path(path).resolve())
    return config.stash[_execution_key]


@pytest.fixture(scope="session")
def ns(pytestconfig):
    """The submission's global variables after it ran."""
    return Namespace(_execution(pytestconfig).namespace)


@pytest.fixture(scope="session")
def src(pytestconfig):
    """The submission's code, for checking how something was computed (see autograde/source.py)."""
    return Source(_execution(pytestconfig).statements)


@pytest.fixture(scope="session")
def exec_errors(pytestconfig):
    """Statements that failed while running the submission: [{"line", "error"}]."""
    return list(_execution(pytestconfig).failures)


def _message(report):
    crash = getattr(report.longrepr, "reprcrash", None)
    text = crash.message if crash else str(report.longrepr)
    text = text.strip().split("\n")[0]  # drop pytest's "+ where ..." explanation lines
    text = " ".join(text.split())
    return text if len(text) <= 300 else text[:297] + "..."


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    results = item.config.stash[_results_key]
    if report.failed or report.skipped:  # setup errors (e.g. fixture failure) count as failures
        results.setdefault(item.nodeid, {"passed": False, "message": _message(report)})
    elif report.when == "call":
        results.setdefault(item.nodeid, {"passed": True, "message": ""})
    return report


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    out = config.getoption("--results-json")
    if not out or _meta_key not in config.stash:
        return
    results = config.stash[_results_key]
    execution = config.stash.get(_execution_key, None)
    tests = []
    for test, item in zip(config.stash[_meta_key]["tests"], session.items):
        result = results.get(item.nodeid, {"passed": False, "message": "did not run"})
        tests.append({**test, **result})
    with open(out, "w") as f:
        json.dump({
            **config.stash[_meta_key],
            "tests": tests,
            "exec_errors": execution.failures if execution else [],
            "from_ipynb": execution.from_ipynb if execution else False,
        }, f)
