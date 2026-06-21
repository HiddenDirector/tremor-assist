from __future__ import annotations

import math


class _LowPassFilter:
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
    if cutoff <= 0.0:
        return 1.0
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.02, d_cutoff: float = 1.0) -> None:
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
        if self._last_time is not None and timestamp > self._last_time:
            dt = timestamp - self._last_time
        else:
            dt = 1.0 / 60.0
        self._last_time = timestamp

        if self._x.has_last():
            dvalue = (value - self._x.last_raw()) / dt
        else:
            dvalue = 0.0
        edvalue = self._dx.filter(dvalue, _smoothing_alpha(self.d_cutoff, dt))

        cutoff = self.min_cutoff + self.beta * abs(edvalue)
        return self._x.filter(value, _smoothing_alpha(cutoff, dt))


class Deadzone2D:

    def __init__(self, radius: float = 1.5) -> None:
        self.radius = float(radius)
        self.anchor: tuple[float, float] | None = None

    def set_radius(self, radius: float) -> None:
        self.radius = float(radius)

    def reset(self, point: tuple[float, float] | None = None) -> None:
        self.anchor = point

    def apply(self, x: float, y: float) -> tuple[float, float]:
        if self.anchor is None:
            self.anchor = (x, y)
            return self.anchor
        dx = x - self.anchor[0]
        dy = y - self.anchor[1]
        dist = math.hypot(dx, dy)
        if dist <= self.radius or dist == 0.0:
            return self.anchor
        k = (dist - self.radius) / dist
        self.anchor = (self.anchor[0] + dx * k, self.anchor[1] + dy * k)
        return self.anchor


class ScrollStabilizer:

    def __init__(self, reversal_ms: float = 120.0, reversal_max: float = 1.0) -> None:
        self.reversal_ms = float(reversal_ms)
        self.reversal_max = float(reversal_max)
        self._last_dir = 0
        self._last_time: float | None = None

    def set_params(self, reversal_ms: float, reversal_max: float) -> None:
        self.reversal_ms = float(reversal_ms)
        self.reversal_max = float(reversal_max)

    def reset(self) -> None:
        self._last_dir = 0
        self._last_time = None

    def filter(self, delta: float, now: float) -> float:
        if delta == 0.0:
            return 0.0
        direction = 1 if delta > 0 else -1
        if (
            self._last_dir != 0
            and direction != self._last_dir
            and self._last_time is not None
            and (now - self._last_time) * 1000.0 < self.reversal_ms
            and abs(delta) <= self.reversal_max
        ):
            self._last_time = now
            return 0.0
        self._last_dir = direction
        self._last_time = now
        return delta


class OneEuroFilter2D:
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


def _native():
    try:
        from . import native
    except Exception:
        return None
    return native if native.CORE_AVAILABLE else None


def make_filter2d(min_cutoff: float = 1.0, beta: float = 0.02, d_cutoff: float = 1.0):
    n = _native()
    if n is not None:
        return n.NativeOneEuroFilter2D(min_cutoff, beta, d_cutoff)
    return OneEuroFilter2D(min_cutoff, beta, d_cutoff)


def make_deadzone(radius: float = 1.5):
    n = _native()
    if n is not None:
        return n.NativeDeadzone2D(radius)
    return Deadzone2D(radius)


def make_scroll(reversal_ms: float = 120.0, reversal_max: float = 1.0):
    n = _native()
    if n is not None:
        return n.NativeScrollStabilizer(reversal_ms, reversal_max)
    return ScrollStabilizer(reversal_ms, reversal_max)


def native_backend() -> str:
    return "native (C/Swift)" if _native() is not None else "python"
