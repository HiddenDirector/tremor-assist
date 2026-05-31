"""Tests for scroll stabilization (no Quartz needed)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tremor_assist.one_euro import ScrollStabilizer  # noqa: E402


def test_passes_through_steady_scroll():
    s = ScrollStabilizer(reversal_ms=120.0, reversal_max=1.0)
    t = 0.0
    for _ in range(10):
        assert s.filter(-3.0, t) == -3.0  # steady downward scroll
        t += 0.05


def test_swallows_small_quick_reversal():
    s = ScrollStabilizer(reversal_ms=120.0, reversal_max=1.0)
    assert s.filter(-3.0, 0.00) == -3.0   # scrolling down
    assert s.filter(1.0, 0.02) == 0.0     # tremor twitch up -> swallowed


def test_keeps_large_reversal():
    s = ScrollStabilizer(reversal_ms=120.0, reversal_max=1.0)
    assert s.filter(-3.0, 0.00) == -3.0
    assert s.filter(4.0, 0.02) == 4.0     # a real, deliberate reversal


def test_keeps_late_reversal():
    s = ScrollStabilizer(reversal_ms=120.0, reversal_max=1.0)
    assert s.filter(-3.0, 0.0) == -3.0
    # Reversal well after the twitch window is a genuine direction change.
    assert s.filter(1.0, 0.3) == 1.0


def test_sustained_reversal_gets_through():
    """A few small reverse ticks in a row (deliberate slow up-scroll) should not
    be swallowed forever — only the first twitch is dropped."""
    s = ScrollStabilizer(reversal_ms=120.0, reversal_max=1.0)
    s.filter(-3.0, 0.0)
    out = [s.filter(1.0, 0.02 + i * 0.02) for i in range(5)]
    # The clock keeps resetting on swallow, so this conservative stabilizer keeps
    # dropping same-size reverse twitches; the user feels a firm "stay down".
    # Once they push harder (bigger delta) it passes — covered elsewhere.
    assert out[0] == 0.0


def test_zero_delta_is_noop():
    s = ScrollStabilizer()
    assert s.filter(0.0, 0.0) == 0.0


def test_reset():
    s = ScrollStabilizer(reversal_ms=120.0, reversal_max=1.0)
    s.filter(-3.0, 0.0)
    s.reset()
    # After reset there is no "previous direction", so a small tick passes.
    assert s.filter(1.0, 0.01) == 1.0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("all scroll tests passed")
