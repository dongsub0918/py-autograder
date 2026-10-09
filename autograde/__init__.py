"""Helpers for writing a week's test file.

    from autograde import points, assert_matches

    @points(10)
    def test_seq2(ns):
        assert_matches(ns.seq2, [2, 6, 10, 14, 18, 22, 26])
"""

import numpy as np
import pytest


def points(n):
    """Mark a test as worth `n` points."""
    return pytest.mark.points(n)


def assert_matches(actual, expected, rtol=1e-7):
    """Numbers/arrays/lists/pandas columns equal in shape and value (within `rtol`).
    A list and a numpy array with the same numbers match."""
    a, e = np.asarray(actual), np.asarray(expected)
    shown = " ".join(repr(actual).split())
    assert a.shape == e.shape, f"got {shown} (shape {a.shape}), expected shape {e.shape}"
    try:
        close = np.allclose(a, e, rtol=rtol, atol=0)
    except TypeError:  # non-numeric values
        close = False
    assert close, f"got {shown}, expected {' '.join(repr(e).split())}"
