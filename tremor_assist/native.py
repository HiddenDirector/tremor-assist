from __future__ import annotations

import ctypes
import os
from ctypes import POINTER, c_char_p, c_double, c_int, c_uint64, c_void_p

_DIR = os.path.dirname(os.path.abspath(__file__))
_SEARCH = [
    os.path.join(_DIR, "..", "native", "build"),
    os.path.join(_DIR, "_native"),
    _DIR,
]


def _find(name: str) -> str | None:
    env = os.environ.get("TREMOR_NATIVE_DIR")
    dirs = [env, *_SEARCH] if env else _SEARCH
    for d in dirs:
        if not d:
            continue
        path = os.path.join(d, name)
        if os.path.exists(path):
            return path
    return None


def _load_core() -> ctypes.CDLL | None:
    if os.environ.get("TREMOR_NO_NATIVE"):
        return None
    path = _find("libtremorcore.dylib")
    if not path:
        return None
    try:
        lib = ctypes.CDLL(path)
    except OSError:
        return None

    lib.te_oneeuro2d_new.restype = c_void_p
    lib.te_oneeuro2d_new.argtypes = [c_double, c_double, c_double]
    lib.te_oneeuro2d_update_params.argtypes = [c_void_p, c_double, c_double, c_double]
    lib.te_oneeuro2d_reset.argtypes = [c_void_p]
    lib.te_oneeuro2d_filter.argtypes = [
        c_void_p, c_double, c_double, c_double, POINTER(c_double), POINTER(c_double)
    ]
    lib.te_oneeuro2d_free.argtypes = [c_void_p]

    lib.te_deadzone_new.restype = c_void_p
    lib.te_deadzone_new.argtypes = [c_double]
    lib.te_deadzone_set_radius.argtypes = [c_void_p, c_double]
    lib.te_deadzone_reset.argtypes = [c_void_p, c_int, c_double, c_double]
    lib.te_deadzone_apply.argtypes = [
        c_void_p, c_double, c_double, POINTER(c_double), POINTER(c_double)
    ]
    lib.te_deadzone_free.argtypes = [c_void_p]

    lib.te_scroll_new.restype = c_void_p
    lib.te_scroll_new.argtypes = [c_double, c_double]
    lib.te_scroll_set_params.argtypes = [c_void_p, c_double, c_double]
    lib.te_scroll_reset.argtypes = [c_void_p]
    lib.te_scroll_filter.restype = c_double
    lib.te_scroll_filter.argtypes = [c_void_p, c_double, c_double]
    lib.te_scroll_free.argtypes = [c_void_p]

    lib.te_core_version.restype = c_char_p
    return lib


_CORE = _load_core()
CORE_AVAILABLE = _CORE is not None


def core_version() -> str | None:
    if _CORE is None:
        return None
    return _CORE.te_core_version().decode()


class NativeOneEuroFilter2D:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.02, d_cutoff: float = 1.0) -> None:
        assert _CORE is not None
        self._h = _CORE.te_oneeuro2d_new(float(min_cutoff), float(beta), float(d_cutoff))
        self._ox = c_double()
        self._oy = c_double()

    def update_params(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0) -> None:
        _CORE.te_oneeuro2d_update_params(self._h, float(min_cutoff), float(beta), float(d_cutoff))

    def reset(self) -> None:
        _CORE.te_oneeuro2d_reset(self._h)

    def filter(self, x: float, y: float, timestamp: float) -> tuple[float, float]:
        _CORE.te_oneeuro2d_filter(self._h, x, y, timestamp,
                                  ctypes.byref(self._ox), ctypes.byref(self._oy))
        return self._ox.value, self._oy.value

    def __del__(self) -> None:
        if getattr(self, "_h", None) and _CORE is not None:
            _CORE.te_oneeuro2d_free(self._h)
            self._h = None


class NativeDeadzone2D:
    def __init__(self, radius: float = 1.5) -> None:
        assert _CORE is not None
        self._h = _CORE.te_deadzone_new(float(radius))
        self._ox = c_double()
        self._oy = c_double()

    def set_radius(self, radius: float) -> None:
        _CORE.te_deadzone_set_radius(self._h, float(radius))

    def reset(self, point: tuple[float, float] | None = None) -> None:
        if point is None:
            _CORE.te_deadzone_reset(self._h, 0, 0.0, 0.0)
        else:
            _CORE.te_deadzone_reset(self._h, 1, float(point[0]), float(point[1]))

    def apply(self, x: float, y: float) -> tuple[float, float]:
        _CORE.te_deadzone_apply(self._h, x, y, ctypes.byref(self._ox), ctypes.byref(self._oy))
        return self._ox.value, self._oy.value

    def __del__(self) -> None:
        if getattr(self, "_h", None) and _CORE is not None:
            _CORE.te_deadzone_free(self._h)
            self._h = None


class NativeScrollStabilizer:
    def __init__(self, reversal_ms: float = 120.0, reversal_max: float = 1.0) -> None:
        assert _CORE is not None
        self._h = _CORE.te_scroll_new(float(reversal_ms), float(reversal_max))

    def set_params(self, reversal_ms: float, reversal_max: float) -> None:
        _CORE.te_scroll_set_params(self._h, float(reversal_ms), float(reversal_max))

    def reset(self) -> None:
        _CORE.te_scroll_reset(self._h)

    def filter(self, delta: float, now: float) -> float:
        return _CORE.te_scroll_filter(self._h, delta, now)

    def __del__(self) -> None:
        if getattr(self, "_h", None) and _CORE is not None:
            _CORE.te_scroll_free(self._h)
            self._h = None


def _load_engine() -> ctypes.CDLL | None:
    if os.environ.get("TREMOR_NO_NATIVE"):
        return None
    path = _find("libtremorengine.dylib")
    if not path:
        return None
    try:
        lib = ctypes.CDLL(path)
    except OSError:
        return None
    lib.te_engine_start.restype = c_int
    lib.te_engine_configure.argtypes = [c_double, c_double, c_double, c_double]
    lib.te_engine_set_enabled.argtypes = [c_int]
    lib.te_engine_events_smoothed.restype = c_uint64
    return lib


_ENGINE = _load_engine()
ENGINE_AVAILABLE = _ENGINE is not None


class NativeTap:
    """Driver for the Swift CGEventTap engine (libtremorengine.dylib).

    The whole per-event smoothing path lives in native code; Python only
    starts/stops it and pushes config. start() returns 0 on success or -1 if
    the event tap could not be created (usually missing Accessibility).
    """

    def start(self) -> int:
        return int(_ENGINE.te_engine_start())

    def stop(self) -> None:
        _ENGINE.te_engine_stop()

    def configure(
        self, min_cutoff: float, beta: float, d_cutoff: float, deadzone_px: float
    ) -> None:
        _ENGINE.te_engine_configure(float(min_cutoff), float(beta),
                                    float(d_cutoff), float(deadzone_px))

    def set_enabled(self, on: bool) -> None:
        _ENGINE.te_engine_set_enabled(1 if on else 0)

    def events_smoothed(self) -> int:
        return int(_ENGINE.te_engine_events_smoothed())
