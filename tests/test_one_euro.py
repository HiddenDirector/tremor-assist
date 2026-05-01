"""Tests for the One Euro Filter — these run on any platform (no Quartz needed)."""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tremor_assist.one_euro import OneEuroFilter, OneEuroFilter2D  # noqa: E402


def test_passthrough_first_sample():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.02)
    assert f.filter(5.0, 0.0) == 5.0


def test_reduces_jitter_on_still_hand():
    """A still hand with tremor noise should come out far steadier."""
    random.seed(1)
    f = OneEuroFilter(min_cutoff=0.5, beta=0.005)
    t = 0.0
    dt = 1.0 / 120.0
    raw_dev = 0.0
    filt_dev = 0.0
    prev_raw = None
    prev_filt = None
    for _ in range(600):
        raw = 100.0 + random.uniform(-3.0, 3.0)  # tremor around a fixed point
        filt = f.filter(raw, t)
        if prev_raw is not None:
            raw_dev += abs(raw - prev_raw)
            filt_dev += abs(filt - prev_filt)
        prev_raw, prev_filt = raw, filt
        t += dt
    # Sample-to-sample motion (the felt jitter) should be dramatically reduced.
    assert filt_dev < raw_dev * 0.25


def test_tracks_fast_movement():
    """During fast deliberate motion the filter should stay close to the target."""
    f = OneEuroFilter(min_cutoff=1.0, beta=0.05)
    t = 0.0
    dt = 1.0 / 120.0
    last = 0.0
    for i in range(240):
        target = i * 5.0  # steadily moving fast
        last = f.filter(target, t)
        t += dt
    # Should be tracking within a small fraction of the total travel.
    assert abs(last - (239 * 5.0)) < 60.0


def test_2d_independent_axes():
    f = OneEuroFilter2D(1.0, 0.02)
    x, y = f.filter(3.0, 7.0, 0.0)
    assert x == 3.0 and y == 7.0


if __name__ == "__main__":
    test_passthrough_first_sample()
    test_reduces_jitter_on_still_hand()
    test_tracks_fast_movement()
    test_2d_independent_axes()
    print("all tests passed")
