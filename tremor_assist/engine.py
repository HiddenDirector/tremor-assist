"""System-wide input filtering engine built on a Quartz CGEventTap.

The engine installs a single event tap that sees mouse-move, mouse-drag,
mouse-button and key events before they reach the focused application. It:

  * smooths pointer motion with a One Euro Filter (kills tremor jitter while
    keeping deliberate movement responsive);
  * debounces keyboard key-downs (a tremor can make one intended press
    register as several);
  * debounces mouse clicks (prevents accidental double-clicks / misfires).

It requires macOS Accessibility permission for the host process (the Python
interpreter / Terminal). Without it, ``Quartz.CGEventTapCreate`` returns None
and we surface a clear error.

The tap runs its CFRunLoop on a dedicated background thread so a GUI can own
the main thread. The callback only reads from a shared ``Settings`` object,
so live parameter changes take effect immediately and lock-free.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import Quartz

from .config import Settings
from .one_euro import OneEuroFilter2D

# Event types we tap. Pointer motion (moved + the three drag variants) is
# smoothed; button-downs are debounced; key events are debounced.
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
_KEY_DOWN_TYPE = Quartz.kCGEventKeyDown


def _event_mask(*types: int) -> int:
    mask = 0
    for t in types:
        mask |= Quartz.CGEventMaskBit(t)
    return mask


class TremorEngine:
    def __init__(self, settings: Settings, on_status: Optional[Callable[[str], None]] = None) -> None:
        self.settings = settings
        self._on_status = on_status or (lambda _msg: None)

        self._filter = OneEuroFilter2D(settings.min_cutoff, settings.beta, settings.d_cutoff)
        self._last_filtered: Optional[tuple[float, float]] = None

        # Debounce bookkeeping (monotonic seconds).
        self._last_keydown: dict[int, float] = {}
        self._last_click: dict[int, float] = {}

        # Lightweight live stats for the UI.
        self.events_smoothed = 0
        self.keys_suppressed = 0
        self.clicks_suppressed = 0

        # --- Tracking metrics ---
        # Total distance the cursor *would* have travelled (raw) vs. the
        # distance it actually travelled after smoothing. The difference is the
        # jitter we erased.
        self.raw_path_px = 0.0
        self.filtered_path_px = 0.0
        self._last_raw: Optional[tuple[float, float]] = None
        # Per-move tremor amplitude = how far the raw point sat from the
        # smoothed point. Kept in a fixed ring buffer for a live graph.
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
        self._run_loop_source = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ----------------------------------------------------------------- lifecycle
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
            # Wake the run loop so CFRunLoopRun() returns and the thread exits.
            Quartz.CFRunLoopStop(self._run_loop)

    # ------------------------------------------------------------------- internals
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

        # Two independent taps with different permission requirements:
        #   * Pointer events  -> Accessibility permission
        #   * Keyboard events -> Input Monitoring permission
        # Splitting them means mouse smoothing still works if only one is
        # granted, instead of an all-or-nothing failure.
        mouse_mask = _event_mask(*_MOUSE_MOVE_TYPES, *_MOUSE_DOWN_TYPES)
        self._mouse_tap, self._mouse_source = self._make_tap(mouse_mask)
        self._key_tap, self._key_source = self._make_tap(_event_mask(_KEY_DOWN_TYPE))

        self.mouse_active = self._mouse_tap is not None
        self.keyboard_active = self._key_tap is not None
        # Keep the legacy attribute pointing at whatever we have, for teardown.
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

        Quartz.CFRunLoopRun()  # blocks until CFRunLoopStop

        # Teardown.
        for tap in (self._mouse_tap, self._key_tap):
            if tap:
                Quartz.CGEventTapEnable(tap, False)
        self._running = False
        self._on_status("STOPPED")

    # The callback runs on the tap thread for every matching event.
    def _callback(self, proxy, event_type, event, refcon):
        try:
            # The system disables a tap that takes too long or after certain
            # input; re-enable both and pass the event through untouched.
            if event_type in (
                Quartz.kCGEventTapDisabledByTimeout,
                Quartz.kCGEventTapDisabledByUserInput,
            ):
                for tap in (getattr(self, "_mouse_tap", None), getattr(self, "_key_tap", None)):
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
            if event_type == _KEY_DOWN_TYPE:
                return self._handle_key_down(event)
            return event
        except Exception:
            # Never let an exception kill the tap — fail open (pass event).
            return event

    def _handle_mouse_move(self, event):
        s = self.settings
        if not s.smoothing_enabled:
            self._last_filtered = None
            self._last_raw = None
            return event

        self._filter.update_params(s.min_cutoff, s.beta, s.d_cutoff)
        loc = Quartz.CGEventGetLocation(event)
        now = time.monotonic()
        fx, fy = self._filter.filter(loc.x, loc.y, now)

        Quartz.CGEventSetLocation(event, Quartz.CGPointMake(fx, fy))
        # Also smooth the relative deltas some games read directly.
        if self._last_filtered is not None:
            Quartz.CGEventSetIntegerValueField(
                event, Quartz.kCGMouseEventDeltaX, int(round(fx - self._last_filtered[0]))
            )
            Quartz.CGEventSetIntegerValueField(
                event, Quartz.kCGMouseEventDeltaY, int(round(fy - self._last_filtered[1]))
            )

        # --- tracking ---
        if self._last_raw is not None:
            self.raw_path_px += math.hypot(loc.x - self._last_raw[0], loc.y - self._last_raw[1])
        if self._last_filtered is not None:
            self.filtered_path_px += math.hypot(fx - self._last_filtered[0], fy - self._last_filtered[1])
        amp = math.hypot(loc.x - fx, loc.y - fy)
        self._tremor_buf[self._tremor_idx] = amp
        self._tremor_idx = (self._tremor_idx + 1) % self._tremor_capacity
        if amp > self.peak_tremor_px:
            self.peak_tremor_px = amp

        self._last_raw = (loc.x, loc.y)
        self._last_filtered = (fx, fy)
        self.events_smoothed += 1
        return event

    # ------------------------------------------------------------------- tracking
    def tremor_recent(self):
        """Snapshot of the recent per-move tremor amplitudes, oldest-first."""
        i = self._tremor_idx
        buf = self._tremor_buf
        return buf[i:] + buf[:i]

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
        """Primitive-only snapshot for persisting a session record."""
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
        }

    def _handle_mouse_down(self, event_type, event):
        s = self.settings
        if not s.click_debounce_enabled:
            return event
        now = time.monotonic()
        last = self._last_click.get(event_type)
        window = s.click_debounce_ms / 1000.0
        if last is not None and (now - last) < window:
            self.clicks_suppressed += 1
            return None  # swallow the bounce
        self._last_click[event_type] = now
        return event

    def _handle_key_down(self, event):
        s = self.settings
        if not s.debounce_enabled:
            return event
        # Never debounce auto-repeat (holding a key to keep moving/firing).
        if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat):
            return event
        keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        now = time.monotonic()
        last = self._last_keydown.get(keycode)
        window = s.debounce_ms / 1000.0
        if last is not None and (now - last) < window:
            self.keys_suppressed += 1
            return None  # swallow the bounce
        self._last_keydown[keycode] = now
        return event
