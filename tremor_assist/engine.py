from __future__ import annotations

import math
import threading
import time
from typing import Callable

import Quartz

from .adaptive import AdaptiveController
from .analysis import TremorAnalyzer
from .config import Settings
from .one_euro import Deadzone2D, OneEuroFilter2D, ScrollStabilizer

_MOUSE_MOVE_TYPES = {
    Quartz.kCGEventMouseMoved,
    Quartz.kCGEventLeftMouseDragged,
    Quartz.kCGEventRightMouseDragged,
    Quartz.kCGEventOtherMouseDragged,
}
_MOUSE_DOWN_TYPES = {
    Quartz.kCGEventLeftMouseDown,
    Quartz.kCGEventRightMouseDown,
    Quartz.kCGEventOtherMouseDown,
}
_SCROLL_TYPE = Quartz.kCGEventScrollWheel
_KEY_DOWN_TYPE = Quartz.kCGEventKeyDown


def _event_mask(*types: int) -> int:
    mask = 0
    for t in types:
        mask |= Quartz.CGEventMaskBit(t)
    return mask


class TremorEngine:
    def __init__(self, settings: Settings, on_status: Callable[[str], None] | None = None) -> None:
        self.settings = settings
        self._on_status = on_status or (lambda _msg: None)

        self._filter = OneEuroFilter2D(settings.min_cutoff, settings.beta, settings.d_cutoff)
        self._deadzone = Deadzone2D(settings.deadzone_px)
        self._scroll = ScrollStabilizer(settings.scroll_reversal_ms, settings.scroll_reversal_max)
        self._analyzer = TremorAnalyzer()
        self._adaptive = AdaptiveController(deadzone_max=settings.auto_adapt_max_px)
        self._last_move_t: float | None = None
        self._last_output: tuple[float, float] | None = None

        self._lock_until = 0.0
        self._lock_pos: tuple[float, float] | None = None

        self._last_keydown: dict[int, float] = {}
        self._last_click: dict[int, float] = {}

        self.events_smoothed = 0
        self.keys_suppressed = 0
        self.clicks_suppressed = 0
        self.scrolls_suppressed = 0

        self.raw_path_px = 0.0
        self.filtered_path_px = 0.0
        self._last_raw: tuple[float, float] | None = None
        self._tremor_capacity = 180
        self._tremor_buf = [0.0] * self._tremor_capacity
        self._tremor_idx = 0
        self.peak_tremor_px = 0.0
        self.started_at = time.time()

        self._tap = None
        self._mouse_tap = None
        self._key_tap = None
        self._mouse_source = None
        self._key_source = None
        self.mouse_active = False
        self.keyboard_active = False
        self._run_loop = None
        self._thread: threading.Thread | None = None
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._thread = threading.Thread(target=self._run, name="TremorEngineTap", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._run_loop is not None:
            Quartz.CFRunLoopStop(self._run_loop)

    def _make_tap(self, mask):
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._callback,
            None,
        )
        if not tap:
            return None, None
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(tap, True)
        return tap, source

    def _run(self) -> None:
        self._run_loop = Quartz.CFRunLoopGetCurrent()

        # Pointer tap needs Accessibility; keyboard tap needs Input Monitoring.
        # Keep them separate so one works when only one permission is granted.
        mouse_mask = _event_mask(*_MOUSE_MOVE_TYPES, *_MOUSE_DOWN_TYPES, _SCROLL_TYPE)
        self._mouse_tap, self._mouse_source = self._make_tap(mouse_mask)
        self._key_tap, self._key_source = self._make_tap(_event_mask(_KEY_DOWN_TYPE))

        self.mouse_active = self._mouse_tap is not None
        self.keyboard_active = self._key_tap is not None
        self._tap = self._mouse_tap or self._key_tap

        if not self.mouse_active and not self.keyboard_active:
            self._on_status(
                "ACCESSIBILITY_REQUIRED: could not create event tap. Grant "
                "Accessibility (and Input Monitoring) permission to TremorAssist, "
                "then reopen."
            )
            return

        self._running = True
        if self.mouse_active and self.keyboard_active:
            self._on_status("RUNNING")
        elif self.mouse_active:
            self._on_status("RUNNING_MOUSE_ONLY")
        else:
            self._on_status("RUNNING_KEYBOARD_ONLY")

        Quartz.CFRunLoopRun()

        for tap in (self._mouse_tap, self._key_tap):
            if tap:
                Quartz.CGEventTapEnable(tap, False)
        self._running = False
        self._on_status("STOPPED")

    def _callback(self, proxy, event_type, event, refcon):
        try:
            if event_type in (
                Quartz.kCGEventTapDisabledByTimeout,
                Quartz.kCGEventTapDisabledByUserInput,
            ):
                for tap in (self._mouse_tap, self._key_tap):
                    if tap:
                        Quartz.CGEventTapEnable(tap, True)
                return event

            s = self.settings
            if not s.enabled:
                return event

            if event_type in _MOUSE_MOVE_TYPES:
                return self._handle_mouse_move(event)
            if event_type in _MOUSE_DOWN_TYPES:
                return self._handle_mouse_down(event_type, event)
            if event_type == _SCROLL_TYPE:
                return self._handle_scroll(event)
            if event_type == _KEY_DOWN_TYPE:
                return self._handle_key_down(event)
            return event
        except Exception:
            return event

    def _handle_mouse_move(self, event):
        s = self.settings
        loc = Quartz.CGEventGetLocation(event)
        now = time.monotonic()

        # Freeze the aim point for a moment around a click so the tremor-jerk
        # during the press doesn't drag the cursor off target.
        if s.click_lock_enabled and self._lock_pos is not None and now < self._lock_until:
            self._set_output(event, self._lock_pos[0], self._lock_pos[1])
            return event

        if not s.smoothing_enabled:
            self._last_output = None
            self._last_raw = None
            self._deadzone.reset()
            return event

        # Feed the raw path to the tremor analyzer (frequency/amplitude estimate).
        self._analyzer.add(now, loc.x, loc.y)
        analysis = self._analyzer.analyze(now)

        # Pick effective filter / dead-zone parameters. Auto mode runs a closed
        # loop that retunes them from the live tremor estimate; otherwise use the
        # user's chosen values directly.
        if s.auto_adapt_enabled:
            dt = (now - self._last_move_t) if self._last_move_t is not None else 1.0 / 120.0
            cutoff, beta, dz = self._adaptive.update(
                dt, analysis, s.min_cutoff, s.beta, s.deadzone_px, s.auto_adapt_strength)
        else:
            if self._adaptive.state()["cutoff"] is not None:
                self._adaptive.reset()
            cutoff, beta, dz = s.min_cutoff, s.beta, s.deadzone_px
        self._last_move_t = now

        self._filter.update_params(cutoff, beta, s.d_cutoff)
        fx, fy = self._filter.filter(loc.x, loc.y, now)

        if s.deadzone_enabled:
            self._deadzone.set_radius(dz)
            ox, oy = self._deadzone.apply(fx, fy)
        else:
            ox, oy = fx, fy

        if self._last_raw is not None:
            self.raw_path_px += math.hypot(
                loc.x - self._last_raw[0], loc.y - self._last_raw[1])
        if self._last_output is not None:
            self.filtered_path_px += math.hypot(
                ox - self._last_output[0], oy - self._last_output[1])
        amp = math.hypot(loc.x - ox, loc.y - oy)
        self._tremor_buf[self._tremor_idx] = amp
        self._tremor_idx = (self._tremor_idx + 1) % self._tremor_capacity
        if amp > self.peak_tremor_px:
            self.peak_tremor_px = amp

        self._last_raw = (loc.x, loc.y)
        self._set_output(event, ox, oy)
        self.events_smoothed += 1
        return event

    def _handle_scroll(self, event):
        s = self.settings
        if not s.scroll_stabilize_enabled:
            return event
        self._scroll.set_params(s.scroll_reversal_ms, s.scroll_reversal_max)
        now = time.monotonic()
        d1 = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGScrollWheelEventDeltaAxis1
        )
        if d1 == 0:
            return event
        out = self._scroll.filter(d1, now)
        if out == 0.0:
            self.scrolls_suppressed += 1
            return None
        return event

    def get_analysis(self) -> dict:
        """Latest tremor estimate. Safe to call from the UI thread."""
        return self._analyzer.peek()

    def get_adaptive_state(self) -> dict:
        """What Auto mode is currently doing (effective params + blend). Safe to
        call from the UI thread."""
        st = self._adaptive.state()
        st["active"] = self.settings.auto_adapt_enabled
        return st

    def _set_output(self, event, ox, oy):
        Quartz.CGEventSetLocation(event, Quartz.CGPointMake(ox, oy))
        if self._last_output is not None:
            Quartz.CGEventSetIntegerValueField(
                event, Quartz.kCGMouseEventDeltaX, int(round(ox - self._last_output[0]))
            )
            Quartz.CGEventSetIntegerValueField(
                event, Quartz.kCGMouseEventDeltaY, int(round(oy - self._last_output[1]))
            )
        self._last_output = (ox, oy)

    def _handle_mouse_down(self, event_type, event):
        s = self.settings
        now = time.monotonic()

        last = self._last_click.get(event_type)
        if (s.click_debounce_enabled and last is not None
                and (now - last) < s.click_debounce_ms / 1000.0):
            self.clicks_suppressed += 1
            return None
        self._last_click[event_type] = now

        # Anchor the click at the current (stabilized) cursor position and lock
        # the cursor there briefly so the click lands where it was aimed.
        if s.click_lock_enabled:
            pos = self._last_output or (
                lambda p: (p.x, p.y)
            )(Quartz.CGEventGetLocation(event))
            self._lock_pos = pos
            self._lock_until = now + s.click_lock_ms / 1000.0
            self._deadzone.reset(pos)
            Quartz.CGEventSetLocation(event, Quartz.CGPointMake(pos[0], pos[1]))
        return event

    def _handle_key_down(self, event):
        s = self.settings
        if not s.debounce_enabled:
            return event
        if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat):
            return event
        keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        now = time.monotonic()
        last = self._last_keydown.get(keycode)
        if last is not None and (now - last) < s.debounce_ms / 1000.0:
            self.keys_suppressed += 1
            return None
        self._last_keydown[keycode] = now
        return event

    def tremor_recent(self):
        i = self._tremor_idx
        return self._tremor_buf[i:] + self._tremor_buf[:i]

    def jitter_removed_px(self) -> float:
        return max(0.0, self.raw_path_px - self.filtered_path_px)

    def jitter_removed_pct(self) -> float:
        if self.raw_path_px < 1.0:
            return 0.0
        return 100.0 * self.jitter_removed_px() / self.raw_path_px

    def avg_tremor_px(self) -> float:
        recent = [v for v in self._tremor_buf if v > 0.0]
        return sum(recent) / len(recent) if recent else 0.0

    def snapshot(self) -> dict:
        analysis = self._analyzer.peek()
        return {
            "duration_s": round(time.time() - self.started_at, 1),
            "movements": self.events_smoothed,
            "raw_path_px": round(self.raw_path_px, 1),
            "filtered_path_px": round(self.filtered_path_px, 1),
            "jitter_removed_px": round(self.jitter_removed_px(), 1),
            "jitter_removed_pct": round(self.jitter_removed_pct(), 1),
            "peak_tremor_px": round(self.peak_tremor_px, 1),
            "keys_suppressed": self.keys_suppressed,
            "clicks_suppressed": self.clicks_suppressed,
            "scrolls_suppressed": self.scrolls_suppressed,
            "tremor_freq_hz": analysis.get("freq_hz"),
            "tremor_amp_rms_px": analysis.get("amp_rms_px", 0.0),
        }
