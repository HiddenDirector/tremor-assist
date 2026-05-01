"""One Euro Filter — adaptive low-pass filtering for noisy signals.

Why this filter: hand tremor shows up in pointer data as high-frequency,
low-amplitude noise riding on top of the slow, intentional movement. A plain
low-pass filter can remove the tremor but adds lag that makes aiming feel
mushy. The One Euro Filter adapts its cutoff frequency to the speed of motion:

  * when the hand is nearly still (the regime where tremor dominates) it
    filters aggressively, erasing jitter;
  * when the user makes a fast, deliberate flick it relaxes the filter so the
    cursor keeps up with almost no lag.

Reference: Casiez, Roussel, Vogel, "1€ Filter: A Simple Speed-based Low-pass
Filter for Noisy Input in Interactive Systems" (CHI 2012).

This module is dependency-free and unit-testable on any platform.
"""

from __future__ import annotations

import math


class _LowPassFilter:
    """Exponential moving average with an externally supplied alpha."""

    def __init__(self) -> None:
        self._initialized = False
        self._prev_raw = 0.0
        self._prev_filtered = 0.0

    def has_last(self) -> bool:
        return self._initialized

    def last_raw(self) -> float:
        return self._prev_raw

    def filter(self, value: float, alpha: float) -> float:
        if self._initialized:
            filtered = alpha * value + (1.0 - alpha) * self._prev_filtered
        else:
            filtered = value
            self._initialized = True
        self._prev_raw = value
        self._prev_filtered = filtered
        return filtered

    def reset(self) -> None:
        self._initialized = False
        self._prev_raw = 0.0
        self._prev_filtered = 0.0


def _smoothing_alpha(cutoff: float, dt: float) -> float:
    """Convert a cutoff frequency (Hz) and timestep into an EMA alpha in (0,1]."""
    if cutoff <= 0.0:
        return 1.0
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    """One Euro Filter for a single scalar channel.

    Parameters
    ----------
    min_cutoff:
        Baseline cutoff frequency in Hz. Lower => more smoothing of slow
        movements (kills more tremor, adds more lag at low speed). Typical
        tremor-assist range: 0.3 – 2.0.
    beta:
        Speed coefficient. Higher => the filter opens up faster as the hand
        moves, reducing lag during deliberate motion. Typical: 0.005 – 0.05.
    d_cutoff:
        Cutoff for the derivative (speed) estimate itself. 1.0 is a good default.
    """

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.02,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self._x = _LowPassFilter()
        self._dx = _LowPassFilter()
        self._last_time: float | None = None

    def reset(self) -> None:
        self._x.reset()
        self._dx.reset()
        self._last_time = None

    def filter(self, value: float, timestamp: float) -> float:
        """Filter ``value`` sampled at ``timestamp`` (seconds)."""
        if self._last_time is not None and timestamp > self._last_time:
            dt = timestamp - self._last_time
        else:
            # First sample, or non-monotonic clock: assume 60 Hz.
            dt = 1.0 / 60.0
        self._last_time = timestamp

        # Estimate the rate of change and low-pass it.
        if self._x.has_last():
            dvalue = (value - self._x.last_raw()) / dt
        else:
            dvalue = 0.0
        edvalue = self._dx.filter(dvalue, _smoothing_alpha(self.d_cutoff, dt))

        # Speed-dependent cutoff: faster motion -> higher cutoff -> less lag.
        cutoff = self.min_cutoff + self.beta * abs(edvalue)
        return self._x.filter(value, _smoothing_alpha(cutoff, dt))


class OneEuroFilter2D:
    """Convenience wrapper applying an independent One Euro Filter per axis."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.02, d_cutoff: float = 1.0) -> None:
        self._fx = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self._fy = OneEuroFilter(min_cutoff, beta, d_cutoff)

    def update_params(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0) -> None:
        for f in (self._fx, self._fy):
            f.min_cutoff = float(min_cutoff)
            f.beta = float(beta)
            f.d_cutoff = float(d_cutoff)

    def reset(self) -> None:
        self._fx.reset()
        self._fy.reset()

    def filter(self, x: float, y: float, timestamp: float) -> tuple[float, float]:
        return self._fx.filter(x, timestamp), self._fy.filter(y, timestamp)
