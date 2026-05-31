"""Tests for tremor frequency/amplitude analysis (no Quartz needed)."""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tremor_assist.analysis import TremorAnalyzer, _classify, _detrend  # noqa: E402


def _feed_sine(analyzer, freq_hz, amp_px, seconds=2.0, fs=200.0, jitter=True, drift=0.0):
    """Feed a synthetic shaking hand: a sinusoid at ``freq_hz`` on the x axis,
    optionally with non-uniform sampling and a deliberate linear drift."""
    random.seed(7)
    n = int(seconds * fs)
    t = 0.0
    for _i in range(n):
        dt = 1.0 / fs
        if jitter:  # emulate uneven mouse event timing
            dt *= random.uniform(0.6, 1.4)
        t += dt
        x = 500.0 + amp_px * math.sin(2 * math.pi * freq_hz * t) + drift * t
        analyzer.add(t, x, 300.0)
    return t


def test_detects_essential_tremor_frequency():
    a = TremorAnalyzer(window_s=2.0, recompute_every=0.0)
    _feed_sine(a, freq_hz=7.0, amp_px=4.0)
    res = a.analyze()
    assert res["freq_hz"] is not None
    assert abs(res["freq_hz"] - 7.0) < 0.6
    assert res["confidence"] > 0.5
    assert "action-range" in res["band"]


def test_detects_parkinsonian_range():
    a = TremorAnalyzer(window_s=2.0, recompute_every=0.0)
    _feed_sine(a, freq_hz=4.5, amp_px=5.0)
    res = a.analyze()
    assert abs(res["freq_hz"] - 4.5) < 0.6
    assert "rest-range" in res["band"]


def test_amplitude_tracks_signal():
    small = TremorAnalyzer(recompute_every=0.0)
    big = TremorAnalyzer(recompute_every=0.0)
    _feed_sine(small, 8.0, amp_px=1.0)
    _feed_sine(big, 8.0, amp_px=6.0)
    assert big.analyze()["amp_rms_px"] > small.analyze()["amp_rms_px"] * 3


def test_deliberate_drift_is_ignored():
    """A steady fast drag with no tremor must NOT register as tremor."""
    a = TremorAnalyzer(recompute_every=0.0)
    # Pure linear motion (deliberate aim), zero oscillation.
    for i in range(400):
        t = i / 200.0
        a.add(t, 100.0 + 800.0 * t, 100.0 + 400.0 * t)
    res = a.analyze()
    assert res["freq_hz"] is None or res["confidence"] < 0.35


def test_drift_plus_tremor_recovers_tremor():
    """Deliberate drift on top of a real 6 Hz tremor: detrending should still
    recover the tremor frequency."""
    a = TremorAnalyzer(recompute_every=0.0)
    _feed_sine(a, freq_hz=6.0, amp_px=4.0, drift=300.0)
    res = a.analyze()
    assert res["freq_hz"] is not None
    assert abs(res["freq_hz"] - 6.0) < 0.8


def test_broadband_noise_has_low_confidence():
    a = TremorAnalyzer(recompute_every=0.0)
    random.seed(11)
    for i in range(400):
        t = i / 200.0
        a.add(t, 500.0 + random.uniform(-4, 4), 300.0 + random.uniform(-4, 4))
    res = a.analyze()
    # No single dominant oscillation -> spectrum is spread out.
    assert res["confidence"] < 0.5


def test_recompute_throttling():
    a = TremorAnalyzer(recompute_every=0.5)
    _feed_sine(a, 7.0, 4.0)
    first = a.analyze(now=10.0)
    # Within the throttle window the cached result is returned unchanged.
    assert a.analyze(now=10.2) is first


def test_insufficient_data_returns_empty():
    a = TremorAnalyzer(recompute_every=0.0)
    a.add(0.0, 1.0, 1.0)
    a.add(0.1, 1.0, 1.0)
    res = a.analyze()
    assert res["freq_hz"] is None
    assert res["band"] == "—"


def test_classify_bands():
    assert _classify(None) == "—"
    assert "rest-range" in _classify(4.0)
    assert "action-range" in _classify(8.0)
    assert _classify(2.0) == "drift"


def test_detrend_removes_line():
    out = _detrend([0.0, 1.0, 2.0, 3.0, 4.0])
    assert all(abs(v) < 1e-9 for v in out)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("all analysis tests passed")
