"""Native macOS (AppKit) control panel for TremorAssist."""

from __future__ import annotations

import os

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelStyleRegularSquare,
    NSBezierPath,
    NSBox,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSOffState,
    NSOnState,
    NSRadioButton,
    NSSlider,
    NSSwitchButton,
    NSTextField,
    NSTimer,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
    NSWorkspace,
)
from Foundation import NSURL, NSObject

from . import config, metrics
from .config import Settings

W = 470          # window width
M = 24           # outer margin
INNER = W - 2 * M

ACCESS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
INPUT_MON_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"

PRESET_INFO = {
    "Mild": "Light touch — smooths small shakes, stays very responsive.",
    "Moderate": "Balanced — a good starting point for most people.",
    "Strong": "Maximum steadiness for stronger tremors.",
    "Auto": "Adapts to how much your hand is shaking, moment to moment.",
    "Off": "No assistance.",
}

PRESET_ORDER = ("Mild", "Moderate", "Strong", "Auto", "Off")


def _rgb(r, g, b):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255, g / 255, b / 255, 1.0)


GREEN = _rgb(30, 166, 114)
GREY = _rgb(154, 163, 173)
RED = _rgb(210, 104, 63)
BLUE = _rgb(47, 123, 232)
TEXT = _rgb(28, 37, 48)
MUTED = _rgb(107, 118, 130)


def _label(text, size=13, bold=False, color=TEXT):
    lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
    lbl.setStringValue_(text)
    lbl.setEditable_(False)
    lbl.setBordered_(False)
    lbl.setDrawsBackground_(False)
    lbl.setSelectable_(False)
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    lbl.setFont_(font)
    lbl.setTextColor_(color)
    return lbl


def _which_preset(settings: Settings):
    for name, overrides in config.PRESETS.items():
        if all(getattr(settings, k) == v for k, v in overrides.items()):
            return name
    return None


class TremorGraphView(NSView):

    def initWithFrame_(self, frame):
        self = objc.super(TremorGraphView, self).initWithFrame_(frame)
        if self is not None:
            self.engine = None
        return self

    def drawRect_(self, rect):
        b = self.bounds()
        w, h = b.size.width, b.size.height
        NSColor.colorWithCalibratedWhite_alpha_(0.96, 1.0).set()
        NSBezierPath.fillRect_(b)
        NSColor.colorWithCalibratedWhite_alpha_(0.85, 1.0).set()
        base = NSBezierPath.bezierPath()
        base.moveToPoint_((0, 2))
        base.lineToPoint_((w, 2))
        base.setLineWidth_(1.0)
        base.stroke()

        eng = getattr(self, "engine", None)
        if eng is None:
            return
        samples = eng.tremor_recent()
        n = len(samples)
        if n < 2:
            return
        scale_max = max(6.0, max(samples))
        pad = 3.0

        def pt(i, v):
            x = w * (i / (n - 1))
            y = pad + min(v / scale_max, 1.0) * (h - 2 * pad)
            return (x, y)

        area = NSBezierPath.bezierPath()
        area.moveToPoint_((0, 2))
        for i, v in enumerate(samples):
            area.lineToPoint_(pt(i, v))
        area.lineToPoint_((w, 2))
        area.closePath()
        NSColor.colorWithCalibratedRed_green_blue_alpha_(47/255, 123/255, 232/255, 0.18).set()
        area.fill()

        line = NSBezierPath.bezierPath()
        line.moveToPoint_(pt(0, samples[0]))
        for i, v in enumerate(samples[1:], start=1):
            line.lineToPoint_(pt(i, v))
        NSColor.colorWithCalibratedRed_green_blue_alpha_(47/255, 123/255, 232/255, 1.0).set()
        line.setLineWidth_(1.5)
        line.stroke()


class Controller(NSObject):
    def initWithSettings_(self, settings):
        self = objc.super(Controller, self).init()
        if self is None:
            return None
        from .engine import TremorEngine

        self.settings = settings
        self._status_msg = "Starting…"
        self._fix_visible = False
        self._advanced_visible = False
        self._radios = {}
        self._sliders = {}
        self._checks = {}
        self._engine = TremorEngine(settings, on_status=self._set_status_msg)
        self._build()
        self._engine.start()
        return self

    @objc.python_method
    def _set_status_msg(self, msg):
        self._status_msg = msg

    @objc.python_method
    def _build(self):
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, 640), style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("TremorAssist")
        self.window.setReleasedWhenClosed_(False)
        self.window.setDelegate_(self)
        self.content = self.window.contentView()

        self.title_lbl = _label("TremorAssist", size=24, bold=True)
        self.sub_lbl = _label("Steadier aim and cleaner key presses while you play.",
                              size=13, color=MUTED)

        self.power_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 52))
        self.power_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        self.power_btn.setFont_(NSFont.boldSystemFontOfSize_(16))
        self.power_btn.setTarget_(self)
        self.power_btn.setAction_("togglePower:")

        self.status_lbl = _label("", size=12, color=MUTED)

        self.fix_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 32))
        self.fix_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        self.fix_btn.setTitle_("1 ▸ Allow Accessibility  (mouse smoothing)")
        self.fix_btn.setBezelColor_(RED)
        self.fix_btn.setTarget_(self)
        self.fix_btn.setAction_("openAccessibility:")

        self.fix_btn2 = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 32))
        self.fix_btn2.setBezelStyle_(NSBezelStyleRegularSquare)
        self.fix_btn2.setTitle_("2 ▸ Allow Input Monitoring  (key/click debounce)")
        self.fix_btn2.setBezelColor_(RED)
        self.fix_btn2.setTarget_(self)
        self.fix_btn2.setAction_("openInputMonitoring:")

        self.sep1 = self._sep()
        self.comfort_hdr = _label("Comfort level", size=15, bold=True)
        self.comfort_sub = _label("Pick how much help you want — change it anytime.",
                                  size=12, color=MUTED)

        selected = _which_preset(self.settings)
        for name in PRESET_ORDER:
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 38))
            btn.setButtonType_(NSRadioButton)
            btn.setTitle_(f"  {name}  —  {PRESET_INFO[name]}")
            btn.setFont_(NSFont.systemFontOfSize_(13))
            btn.setTarget_(self)
            btn.setAction_("radioChanged:")
            btn.setState_(NSOnState if name == selected else NSOffState)
            self._radios[name] = btn

        self.adv_toggle = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 22))
        self.adv_toggle.setBezelStyle_(NSBezelStyleRegularSquare)
        self.adv_toggle.setBordered_(False)
        self.adv_toggle.setFont_(NSFont.systemFontOfSize_(12))
        self.adv_toggle.setTarget_(self)
        self.adv_toggle.setAction_("toggleAdvanced:")
        self.adv_toggle.setContentTintColor_(BLUE) if hasattr(self.adv_toggle, "setContentTintColor_") else None

        self._adv_views = []
        self.chk_smooth = self._check("Smooth mouse movement", 1, self.settings.smoothing_enabled)
        self.lbl_steady = _label("Steadiness   (very steady ◀ ▶ very responsive)", size=12, color=MUTED)
        self.sld_steady = self._slider(1, 0.2, 4.0, self.settings.min_cutoff)
        self.lbl_resp = _label("Fast-move snappiness", size=12, color=MUTED)
        self.sld_resp = self._slider(2, 0.002, 0.08, self.settings.beta)
        self.chk_dead = self._check("Hold steady when still", 5, self.settings.deadzone_enabled)
        self.lbl_dead = _label("Hold strength   (gentle ◀ ▶ rock-solid)", size=12, color=MUTED)
        self.sld_dead = self._slider(5, 0.0, 6.0, self.settings.deadzone_px)
        self.chk_lock = self._check("Steady the aim during a click", 6, self.settings.click_lock_enabled)
        self.lbl_lock = _label("Click steadiness   (off ◀ ▶ long)", size=12, color=MUTED)
        self.sld_lock = self._slider(6, 0.0, 300.0, self.settings.click_lock_ms)
        self.chk_key = self._check("Ignore accidental repeat key presses", 2, self.settings.debounce_enabled)
        self.lbl_key = _label("Key cooldown   (off ◀ ▶ long)", size=12, color=MUTED)
        self.sld_key = self._slider(3, 0.0, 200.0, self.settings.debounce_ms)
        self.chk_click = self._check("Ignore accidental double-clicks", 3, self.settings.click_debounce_enabled)
        self.lbl_click = _label("Click cooldown   (off ◀ ▶ long)", size=12, color=MUTED)
        self.sld_click = self._slider(4, 0.0, 300.0, self.settings.click_debounce_ms)
        self.chk_scroll = self._check("Steady the scroll wheel", 7, self.settings.scroll_stabilize_enabled)
        self.chk_auto = self._check("Auto-adapt to my tremor (recommended)", 8, self.settings.auto_adapt_enabled)
        self._adv_views = [
            self.chk_smooth, self.lbl_steady, self.sld_steady, self.lbl_resp, self.sld_resp,
            self.chk_dead, self.lbl_dead, self.sld_dead,
            self.chk_lock, self.lbl_lock, self.sld_lock,
            self.chk_key, self.lbl_key, self.sld_key, self.chk_click, self.lbl_click, self.sld_click,
            self.chk_scroll, self.chk_auto,
        ]

        self.sep2 = self._sep()
        self.track_hdr = _label("Tracking", size=15, bold=True)
        self.track_sub = _label("Live tremor (taller spikes = more shake caught):",
                                size=12, color=MUTED)
        self.graph = TremorGraphView.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 50))
        self.graph.engine = self._engine
        self.now_lbl = _label("", size=12, color=TEXT)
        self.freq_lbl = _label("", size=12, bold=True, color=BLUE)
        self.session_lbl = _label("", size=12, color=MUTED)
        self.alltime_lbl = _label("", size=12, color=MUTED)
        self._track_views = [
            self.sep2, self.track_hdr, self.track_sub, self.graph,
            self.now_lbl, self.freq_lbl, self.session_lbl, self.alltime_lbl,
        ]

        for v in ([self.title_lbl, self.sub_lbl, self.power_btn, self.status_lbl,
                   self.fix_btn, self.fix_btn2, self.sep1, self.comfort_hdr, self.comfort_sub]
                  + list(self._radios.values())
                  + [self.adv_toggle] + self._adv_views + self._track_views):
            self.content.addSubview_(v)

        self._refresh_power()
        self._relayout()

        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.3, self, "tick:", None, True
        )

    @objc.python_method
    def _sep(self):
        box = NSBox.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 1))
        box.setBoxType_(2)  # NSBoxSeparator
        return box

    @objc.python_method
    def _check(self, title, tag, on):
        b = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 22))
        b.setButtonType_(NSSwitchButton)
        b.setTitle_(title)
        b.setFont_(NSFont.systemFontOfSize_(13))
        b.setTag_(tag)
        b.setState_(NSOnState if on else NSOffState)
        b.setTarget_(self)
        b.setAction_("checkChanged:")
        self._checks[tag] = b
        return b

    @objc.python_method
    def _slider(self, tag, lo, hi, value):
        s = NSSlider.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 20))
        s.setMinValue_(lo)
        s.setMaxValue_(hi)
        s.setFloatValue_(value)
        s.setTag_(tag)
        s.setContinuous_(True)
        s.setTarget_(self)
        s.setAction_("sliderChanged:")
        self._sliders[tag] = s
        return s

    @objc.python_method
    def _relayout(self):
        items = []  # (view, top, height)
        top = 20

        def add(view, h, gap_after=8, x=M, w=INNER):
            nonlocal top
            items.append((view, top, h, x, w))
            top += h + gap_after

        add(self.title_lbl, 30, gap_after=2)
        add(self.sub_lbl, 18, gap_after=16)
        add(self.power_btn, 52, gap_after=8)
        add(self.status_lbl, 34, gap_after=6)
        if self._fix_visible:
            self.fix_btn.setHidden_(False)
            self.fix_btn2.setHidden_(False)
            add(self.fix_btn, 32, gap_after=6)
            add(self.fix_btn2, 32, gap_after=8)
        else:
            self.fix_btn.setHidden_(True)
            self.fix_btn2.setHidden_(True)
        add(self.sep1, 1, gap_after=12)
        add(self.comfort_hdr, 22, gap_after=2)
        add(self.comfort_sub, 16, gap_after=8)
        for name in ("Mild", "Moderate", "Strong", "Off"):
            add(self._radios[name], 26, gap_after=4)
        top += 6
        self.adv_toggle.setTitle_(
            "▾  Hide fine-tuning" if self._advanced_visible else "▸  Fine-tune (optional)"
        )
        add(self.adv_toggle, 20, gap_after=8)

        for v in self._adv_views:
            v.setHidden_(not self._advanced_visible)
        if self._advanced_visible:
            add(self.chk_smooth, 22, gap_after=4)
            add(self.lbl_steady, 16, gap_after=0)
            add(self.sld_steady, 20, gap_after=10)
            add(self.lbl_resp, 16, gap_after=0)
            add(self.sld_resp, 20, gap_after=12)
            add(self.chk_dead, 22, gap_after=4)
            add(self.lbl_dead, 16, gap_after=0)
            add(self.sld_dead, 20, gap_after=12)
            add(self.chk_lock, 22, gap_after=4)
            add(self.lbl_lock, 16, gap_after=0)
            add(self.sld_lock, 20, gap_after=12)
            add(self.chk_key, 22, gap_after=4)
            add(self.lbl_key, 16, gap_after=0)
            add(self.sld_key, 20, gap_after=12)
            add(self.chk_click, 22, gap_after=4)
            add(self.lbl_click, 16, gap_after=0)
            add(self.sld_click, 20, gap_after=12)
            add(self.chk_scroll, 22, gap_after=6)
            add(self.chk_auto, 22, gap_after=4)

        add(self.sep2, 1, gap_after=10)
        add(self.track_hdr, 22, gap_after=2)
        add(self.track_sub, 16, gap_after=4)
        add(self.graph, 50, gap_after=8)
        add(self.now_lbl, 16, gap_after=2)
        add(self.freq_lbl, 16, gap_after=6)
        add(self.session_lbl, 16, gap_after=2)
        add(self.alltime_lbl, 16, gap_after=0)

        total_h = top + M
        self.window.setContentSize_((W, total_h))
        for view, t, h, x, w in items:
            view.setFrame_(NSMakeRect(x, total_h - t - h, w, h))

    def togglePower_(self, sender):
        self.settings.enabled = not self.settings.enabled
        self._refresh_power()
        self._save()

    @objc.python_method
    def _refresh_power(self):
        on = self.settings.enabled
        self.power_btn.setTitle_(
            "✓  Protection is ON   (click to turn off)" if on
            else "Protection is OFF   (click to turn on)"
        )
        self.power_btn.setBezelColor_(GREEN if on else GREY)

    def radioChanged_(self, sender):
        for name, btn in self._radios.items():
            if btn is sender:
                self.applyPresetNamed_(name)
                break

    def applyPresetNamed_(self, name):
        config.apply_preset(self.settings, name)
        self._sync_advanced()
        self._mark_custom()
        self._save()

    @objc.python_method
    def _current_preset(self):
        return _which_preset(self.settings)

    def openAccessibility_(self, sender):
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(ACCESS_URL))

    def openInputMonitoring_(self, sender):
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(INPUT_MON_URL))

    def toggleAdvanced_(self, sender):
        self._advanced_visible = not self._advanced_visible
        self._relayout()

    def checkChanged_(self, sender):
        on = sender.state() == NSOnState
        tag = sender.tag()
        if tag == 1:
            self.settings.smoothing_enabled = on
        elif tag == 2:
            self.settings.debounce_enabled = on
        elif tag == 3:
            self.settings.click_debounce_enabled = on
        elif tag == 5:
            self.settings.deadzone_enabled = on
        elif tag == 6:
            self.settings.click_lock_enabled = on
        elif tag == 7:
            self.settings.scroll_stabilize_enabled = on
        elif tag == 8:
            self.settings.auto_adapt_enabled = on
        self._mark_custom()
        self._save()

    def sliderChanged_(self, sender):
        tag = sender.tag()
        v = float(sender.floatValue())
        if tag == 1:
            self.settings.min_cutoff = v
        elif tag == 2:
            self.settings.beta = v
        elif tag == 3:
            self.settings.debounce_ms = v
        elif tag == 4:
            self.settings.click_debounce_ms = v
        elif tag == 5:
            self.settings.deadzone_px = v
        elif tag == 6:
            self.settings.click_lock_ms = v
        self._mark_custom()
        self._save_soon()

    @objc.python_method
    def _sync_advanced(self):
        self.chk_smooth.setState_(NSOnState if self.settings.smoothing_enabled else NSOffState)
        self.chk_dead.setState_(NSOnState if self.settings.deadzone_enabled else NSOffState)
        self.chk_lock.setState_(NSOnState if self.settings.click_lock_enabled else NSOffState)
        self.chk_key.setState_(NSOnState if self.settings.debounce_enabled else NSOffState)
        self.chk_click.setState_(NSOnState if self.settings.click_debounce_enabled else NSOffState)
        self.chk_scroll.setState_(NSOnState if self.settings.scroll_stabilize_enabled else NSOffState)
        self.chk_auto.setState_(NSOnState if self.settings.auto_adapt_enabled else NSOffState)
        self.sld_steady.setFloatValue_(self.settings.min_cutoff)
        self.sld_resp.setFloatValue_(self.settings.beta)
        self.sld_dead.setFloatValue_(self.settings.deadzone_px)
        self.sld_lock.setFloatValue_(self.settings.click_lock_ms)
        self.sld_key.setFloatValue_(self.settings.debounce_ms)
        self.sld_click.setFloatValue_(self.settings.click_debounce_ms)

    @objc.python_method
    def _mark_custom(self):
        match = _which_preset(self.settings)
        for name, btn in self._radios.items():
            btn.setState_(NSOnState if name == match else NSOffState)

    def tick_(self, timer):
        msg = self._status_msg
        if msg.startswith("ACCESSIBILITY_REQUIRED"):
            self.status_lbl.setStringValue_(
                "⚠  One quick setup step — turn on TremorAssist in the panels "
                "below, then reopen the app."
            )
            self.status_lbl.setTextColor_(RED)
            if not self._fix_visible:
                self._fix_visible = True
                self._relayout()
        elif msg == "RUNNING":
            self.status_lbl.setStringValue_("●  Active and protecting your input.")
            self.status_lbl.setTextColor_(GREEN)
            if self._fix_visible:
                self._fix_visible = False
                self._relayout()
        elif msg == "RUNNING_MOUSE_ONLY":
            self.status_lbl.setStringValue_(
                "●  Mouse smoothing active. For key/click debounce, also allow "
                "Input Monitoring below."
            )
            self.status_lbl.setTextColor_(GREEN)
            if not self._fix_visible:
                self._fix_visible = True
                self._relayout()
        elif msg == "RUNNING_KEYBOARD_ONLY":
            self.status_lbl.setStringValue_(
                "●  Key/click debounce active. For mouse smoothing, also allow "
                "Accessibility below."
            )
            self.status_lbl.setTextColor_(GREEN)
            if not self._fix_visible:
                self._fix_visible = True
                self._relayout()
        elif msg == "STOPPED":
            self.status_lbl.setStringValue_("○  Stopped.")
            self.status_lbl.setTextColor_(MUTED)
        else:
            self.status_lbl.setStringValue_(msg)
            self.status_lbl.setTextColor_(MUTED)

        self._update_tracking()

    @objc.python_method
    def _update_tracking(self):
        e = self._engine
        self.now_lbl.setStringValue_(
            f"Tremor now: {e.avg_tremor_px():.1f} px avg · peak {e.peak_tremor_px:.0f} px"
        )
        self.graph.setNeedsDisplay_(True)

        a = e.get_analysis()
        freq = a.get("freq_hz")
        if freq and a.get("confidence", 0.0) >= 0.35:
            self.freq_lbl.setStringValue_(
                f"Dominant tremor: {freq:.1f} Hz · {a.get('amp_rms_px', 0.0):.1f} px "
                f"— {a.get('band', '')}"
            )
            self.freq_lbl.setTextColor_(BLUE)
        else:
            self.freq_lbl.setStringValue_("Dominant tremor: measuring… (keep moving the mouse)")
            self.freq_lbl.setTextColor_(MUTED)

        self.session_lbl.setStringValue_(
            f"This session: steadied {e.events_smoothed:,} movements · "
            f"{e.jitter_removed_pct():.0f}% jitter removed · "
            f"{e.keys_suppressed} shaky presses · {e.clicks_suppressed} stray clicks · "
            f"{e.scrolls_suppressed} scroll twitches"
        )

        prior = metrics.all_time_totals()
        movements = prior["movements"] + e.events_smoothed
        jitter = prior["jitter_removed_px"] + e.jitter_removed_px()
        keys = prior["keys_suppressed"] + e.keys_suppressed
        sessions = prior["sessions"] + 1
        self.alltime_lbl.setStringValue_(
            f"All time: {movements:,} movements over {sessions} sessions · "
            f"{metrics.humanize_distance_px(jitter)} of shake removed · "
            f"{keys} shaky presses caught"
        )

    _save_pending = False

    @objc.python_method
    def _save(self):
        config.save(self.settings)

    @objc.python_method
    def _save_soon(self):
        if not self._save_pending:
            self._save_pending = True
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.4, self, "doSave:", None, False
            )

    def doSave_(self, timer):
        self._save_pending = False
        self._save()

    def windowShouldClose_(self, sender):
        # Hide to the menu bar; the app keeps running. ⌘Q quits.
        self.window.orderOut_(None)
        self._save()
        return False

    @objc.python_method
    def show(self):
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)


def main():
    first_run = not os.path.exists(config.CONFIG_PATH)
    settings = config.load()

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    controller = Controller.alloc().initWithSettings_(settings)
    controller.show()
    if first_run:
        _show_welcome(controller)
    app.activateIgnoringOtherApps_(True)
    app.run()


def _show_welcome(controller):
    from AppKit import NSAlert

    alert = NSAlert.alloc().init()
    alert.setMessageText_("Welcome to TremorAssist 👋")
    alert.setInformativeText_(
        "Here's all you need to do:\n\n"
        "1.  Pick a comfort level — start with Moderate.\n"
        "2.  If macOS asks, allow permission so we can steady your input.\n"
        "3.  Play your game. Leave this window open in the background.\n\n"
        "Aim feeling laggy? Choose Mild.   Still shaky? Choose Strong."
    )
    alert.addButtonWithTitle_("Let's go")
    alert.runModal()
