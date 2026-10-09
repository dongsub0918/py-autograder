"""Discussion 1: Getting started with Python notebooks.

One test per variable the exercises ask for, all worth the same. Variable names must match
exactly. Exercise 4 reads "0 to 5" as inclusive: y = np.arange(0, 6).
"""

import re

import numpy as np
import statsmodels.api as sm

from autograde import assert_matches, points

CANVAS_COLUMN = "Discussion Assignment 1 (3304388)"
POINTS_POSSIBLE = 100
EACH = POINTS_POSSIBLE / 9

# Exercise 4 inputs
X4 = 7
Y4 = np.arange(0, 6)


# Exercise 1: f-string holding both x (5) and Y (17), in either order, e.g. "x = 5, Y = 17".
# The f-string must read variables: f"x = {5}, Y = {17}" gets the right text but scores 0.
@points(EACH)
def test_ex1_both(ns, src):
    assert isinstance(ns.both, str), f"`both` should be a string, got {ns.both!r}"
    numbers = sorted(int(n) for n in re.findall(r"-?\d+", ns.both))  # any order: "Y = 17, x = 5" is fine
    assert numbers == [5, 17], f"expected both x=5 and Y=17, got {ns.both!r}"
    assert src.fstring_fields("both") is not None, \
        f"`both` should be built with an f-string: both = {src.code_of('both')}"
    hardcoded = src.hardcoded_fields("both")
    assert not hardcoded, f"f-string hard-codes {hardcoded} instead of using variables: both = {src.code_of('both')}"


# Exercise 2: the array 1 to 5.
@points(EACH)
def test_ex2_x_fixed(ns):
    assert_matches(ns.x_fixed, [1, 2, 3, 4, 5])


# Flag only (0 points): the exercise is about fixing np.arange's stop value, but it doesn't
# say np.arange is required, so a hard-coded np.array([1, 2, 3, 4, 5]) isn't penalized.
@points(0)
def test_ex2_x_fixed_uses_arange(src):
    assert "numpy.arange" in src.calls("x_fixed"), \
        f"x_fixed doesn't use np.arange: x_fixed = {src.code_of('x_fixed')}"


# Exercise 3: 2 to 27 by 4s.
@points(EACH)
def test_ex3_seq2(ns):
    assert_matches(ns.seq2, [2, 6, 10, 14, 18, 22, 26])


# Exercise 4: x = 7, y = 0..5.
@points(EACH)
def test_ex4_a(ns):
    assert_matches(ns.a, X4 - Y4)


@points(EACH)
def test_ex4_b(ns):
    assert_matches(ns.b, Y4 - X4)


@points(EACH)
def test_ex4_c(ns):
    assert_matches(ns.c, X4 * Y4)


@points(EACH)
def test_ex4_d(ns):
    assert_matches(ns.d, X4 ** Y4)


@points(EACH)
def test_ex4_e(ns):
    assert_matches(ns.e, Y4 ** X4)


# Exercise 5: dist (ft) converted to meters. Dividing by 3.281 and multiplying by 0.3048
# differ by ~0.005%, so both pass.
@points(EACH)
def test_ex5_dist_m(ns):
    cars = ns.cars
    assert "dist_m" in cars.columns, "`cars` has no `dist_m` column"
    original_dist = sm.datasets.get_rdataset("cars").data["dist"]
    assert_matches(cars["dist_m"], original_dist / 3.281, rtol=1e-3)
