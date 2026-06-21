import math

import pytest

from tremor_assist import native
from tremor_assist.one_euro import Deadzone2D, OneEuroFilter2D, ScrollStabilizer

pytestmark = pytest.mark.skipif(
    not native.CORE_AVAILABLE, reason="native core (libtremorcore.dylib) not built"
)


def _signal(n=2000):
    for i in range(n):
        t = i / 120.0
        x = 100.0 + 30.0 * math.sin(2 * math.pi * 1.5 * t) + 4.0 * math.sin(2 * math.pi * 9 * t)
        y = 80.0 + 20.0 * t + 3.0 * math.cos(2 * math.pi * 8 * t)
        yield x, y, t


def test_oneeuro_matches_python():
    py = OneEuroFilter2D(1.0, 0.02, 1.0)
    na = native.NativeOneEuroFilter2D(1.0, 0.02, 1.0)
    for x, y, t in _signal():
        px, pyv = py.filter(x, y, t)
        nx, ny = na.filter(x, y, t)
        assert nx == pytest.approx(px, abs=1e-9)
        assert ny == pytest.approx(pyv, abs=1e-9)


def test_deadzone_matches_python():
    py = Deadzone2D(1.5)
    na = native.NativeDeadzone2D(1.5)
    for x, y, _ in _signal():
        px, pyv = py.apply(x, y)
        nx, ny = na.apply(x, y)
        assert nx == pytest.approx(px, abs=1e-9)
        assert ny == pytest.approx(pyv, abs=1e-9)


def test_scroll_matches_python():
    py = ScrollStabilizer(120.0, 1.0)
    na = native.NativeScrollStabilizer(120.0, 1.0)
    deltas = [1, 1, -1, 1, -1, -1, 3, -1, 1, -0.5, 0.5, -0.5]
    t = 0.0
    for d in deltas:
        t += 0.01
        assert na.filter(float(d), t) == pytest.approx(py.filter(float(d), t), abs=1e-9)


def test_core_version():
    assert "tremor_core" in (native.core_version() or "")
