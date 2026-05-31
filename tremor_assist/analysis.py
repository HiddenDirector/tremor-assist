"""Tremor signal analysis.

Estimates the *dominant tremor frequency* and amplitude from the live pointer
signal. Pathological tremor is an oscillation in a fairly narrow band:

* Parkinsonian rest tremor   ~3–6 Hz
* Essential / action tremor  ~6–12 Hz
* Physiologic tremor         ~8–12 Hz

Deliberate aiming, by contrast, is low-frequency drift. So we can separate
tremor from intent by detrending the recent pointer path (removing the slow
deliberate component) and looking for a concentrated spectral peak in the
3–14 Hz band.

The math here is deliberately dependency-free (no numpy): a least-squares
detrend, a Hann window, and a direct DFT evaluated on a frequency grid. Mouse
events are not uniformly sampled, so the signal is first linearly resampled
onto a uniform time grid.

This module is pure Python and fully unit-testable without macOS/Quartz.
"""

from __future__ import annotations

import math
from collections import deque

# Tremor search band (Hz). Below this is deliberate movement; above is noise.
FMIN = 3.0
FMAX = 14.0
FSTEP = 0.25
RESAMPLE_HZ = 120.0


def _classify(freq: float | None) -> str:
    """Plain-language band label. Informational, **not** a diagnosis."""
    if freq is None:
        return "—"
    if freq < 3.0:
        return "drift"
    if freq < 6.0:
        return "rest-range (3–6 Hz)"
    if freq <= 12.0:
        return "action-range (6–12 Hz)"
    return "high-frequency"


def _detrend(values: list[float]) -> list[float]:
    """Subtract the least-squares line — removes deliberate slow movement so
    only the oscillation remains."""
    n = len(values)
    if n < 2:
        return [0.0] * n
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    sxx = 0.0
    sxy = 0.0
    for i, v in enumerate(values):
        dx = i - mean_x
        sxx += dx * dx
        sxy += dx * (v - mean_y)
    slope = sxy / sxx if sxx > 0 else 0.0
    intercept = mean_y - slope * mean_x
    return [v - (slope * i + intercept) for i, v in enumerate(values)]


def _hann(n: int) -> list[float]:
    if n < 2:
        return [1.0] * n
    return [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (n - 1)) for i in range(n)]


def _resample_uniform(ts: list[float], vs: list[float], fs: float) -> list[float]:
    """Linear-interpolate an unevenly-sampled signal onto a uniform grid."""
    span = ts[-1] - ts[0]
    n_out = int(span * fs)
    if n_out < 4:
        return []
    out = []
    j = 0
    t0 = ts[0]
    dt = 1.0 / fs
    for k in range(n_out):
        t = t0 + k * dt
        while j < len(ts) - 2 and ts[j + 1] < t:
            j += 1
        t_a, t_b = ts[j], ts[j + 1]
        if t_b <= t_a:
            out.append(vs[j])
            continue
        frac = (t - t_a) / (t_b - t_a)
        frac = 0.0 if frac < 0.0 else 1.0 if frac > 1.0 else frac
        out.append(vs[j] + frac * (vs[j + 1] - vs[j]))
    return out


def _spectrum(sig: list[float], fs: float):
    """Direct DFT power on the tremor frequency grid. Returns (freqs, powers)."""
    n = len(sig)
    win = _hann(n)
    wsig = [s * w for s, w in zip(sig, win)]
    freqs = []
    powers = []
    f = FMIN
    while f <= FMAX + 1e-9:
        w = 2.0 * math.pi * f / fs
        re = 0.0
        im = 0.0
        for idx, s in enumerate(wsig):
            ang = w * idx
            re += s * math.cos(ang)
            im += s * math.sin(ang)
        freqs.append(f)
        powers.append(re * re + im * im)
        f += FSTEP
    return freqs, powers


class TremorAnalyzer:
    """Rolling estimator of dominant tremor frequency, amplitude and confidence.

    Feed raw pointer samples with :meth:`add`; read the latest estimate with
    :meth:`analyze` (results are cached and recomputed at most every
    ``recompute_every`` seconds, so it is cheap to poll from the UI loop).
    """

    def __init__(
        self,
        window_s: float = 2.0,
        recompute_every: float = 0.4,
        fs: float = RESAMPLE_HZ,
    ) -> None:
        self.window_s = float(window_s)
        self.recompute_every = float(recompute_every)
        self.fs = float(fs)
        self._t: deque[float] = deque()
        self._x: deque[float] = deque()
        self._y: deque[float] = deque()
        self._last_compute = 0.0
        self._cached = self._empty()

    @staticmethod
    def _empty() -> dict:
        return {"freq_hz": None, "amp_rms_px": 0.0, "confidence": 0.0, "band": "—"}

    def reset(self) -> None:
        self._t.clear()
        self._x.clear()
        self._y.clear()
        self._cached = self._empty()

    def add(self, t: float, x: float, y: float) -> None:
        self._t.append(t)
        self._x.append(x)
        self._y.append(y)
        cutoff = t - self.window_s
        while self._t and self._t[0] < cutoff:
            self._t.popleft()
            self._x.popleft()
            self._y.popleft()

    def analyze(self, now: float | None = None) -> dict:
        if now is None:
            now = self._t[-1] if self._t else 0.0
        if now - self._last_compute < self.recompute_every:
            return self._cached
        self._last_compute = now
        self._cached = self._compute()
        return self._cached

    # -- internals -----------------------------------------------------------

    def _compute(self) -> dict:
        ts = list(self._t)
        if len(ts) < 8 or (ts[-1] - ts[0]) < 0.6:
            return self._empty()

        xs = _resample_uniform(ts, list(self._x), self.fs)
        ys = _resample_uniform(ts, list(self._y), self.fs)
        if len(xs) < 8:
            return self._empty()

        xs = _detrend(xs)
        ys = _detrend(ys)

        # Total oscillation amplitude (deliberate drift already removed).
        var_x = sum(v * v for v in xs) / len(xs)
        var_y = sum(v * v for v in ys) / len(ys)
        amp_rms = math.sqrt(var_x + var_y)

        fx, px = _spectrum(xs, self.fs)
        _, py = _spectrum(ys, self.fs)
        power = [a + b for a, b in zip(px, py)]
        total = sum(power)
        if total <= 1e-9 or amp_rms < 0.2:
            return {"freq_hz": None, "amp_rms_px": round(amp_rms, 2),
                    "confidence": 0.0, "band": "—"}

        peak_i = max(range(len(power)), key=lambda i: power[i])
        freq = _parabolic_peak(fx, power, peak_i)
        # Confidence = how concentrated the spectrum is around the peak. A pure
        # sinusoid spikes (high); broadband noise spreads out (low).
        peak_mass = power[peak_i]
        if 0 < peak_i < len(power) - 1:
            peak_mass += power[peak_i - 1] + power[peak_i + 1]
        confidence = max(0.0, min(1.0, peak_mass / total))

        return {
            "freq_hz": round(freq, 2),
            "amp_rms_px": round(amp_rms, 2),
            "confidence": round(confidence, 2),
            "band": _classify(freq),
        }


def _parabolic_peak(freqs: list[float], powers: list[float], i: int) -> float:
    """Sub-bin peak location via parabolic interpolation of the 3 points
    around the spectral maximum (sharper than the raw grid resolution)."""
    if i <= 0 or i >= len(powers) - 1:
        return freqs[i]
    a, b, c = powers[i - 1], powers[i], powers[i + 1]
    denom = a - 2.0 * b + c
    if denom == 0:
        return freqs[i]
    offset = 0.5 * (a - c) / denom
    offset = max(-1.0, min(1.0, offset))
    return freqs[i] + offset * (freqs[i + 1] - freqs[i])
