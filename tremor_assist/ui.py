"""Native macOS (Cocoa/AppKit) control panel for TremorAssist.

Why AppKit instead of Tkinter: Apple's deprecated system Tk crashes on recent
macOS versions, and we already depend on pyobjc for the event tap — so the UI
is built natively. That also gives a real macOS look and feel.

Design goals (users have hand tremors and may not be technical):
  * Plain language — "Comfort level", not "min_cutoff".
  * Big targets — a large on/off button and full-width comfort options.
  * Safe defaults — pick a comfort level and you're done; sliders are tucked
    behind an optional "Fine-tune" toggle.
  * Hand-holding — clear status, and a one-click fix if permission is missing.

The AppKit run loop owns the main thread; the engine's event tap runs on its
own thread. The engine reports status by storing a string that a repeating
timer (on the main thread) reads, so there are no cross-thread UI calls.
"""

from __future__ import annotations

import os

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelStyleRegularSquare,
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

from . import config
from .config import Settings

W = 470          # window width
M = 24           # outer margin
INNER = W - 2 * M

ACCESS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

PRESET_INFO = {
    "Mild": "Light touch — smooths small shakes, stays very responsive.",
    "Moderate": "Balanced — a good starting point for most people.",
    "Strong": "Maximum steadiness for stronger tremors.",
    "Off": "No assistance.",
}


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


class Controller(NSObject):
    # ---- construction -------------------------------------------------------
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
        # Called from the tap thread; just stash it. The timer (main thread) reads it.
        self._status_msg = msg

    # ---- UI build -----------------------------------------------------------
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

        # Header.
        self.title_lbl = _label("TremorAssist", size=24, bold=True)
        self.sub_lbl = _label("Steadier aim and cleaner key presses while you play.",
                              size=13, color=MUTED)

        # Big on/off button.
        self.power_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 52))
        self.power_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        self.power_btn.setFont_(NSFont.boldSystemFontOfSize_(16))
        self.power_btn.setTarget_(self)
        self.power_btn.setAction_("togglePower:")

        self.status_lbl = _label("", size=12, color=MUTED)

        self.fix_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 32))
        self.fix_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        self.fix_btn.setTitle_("Fix this — open Accessibility settings")
        self.fix_btn.setBezelColor_(RED)
        self.fix_btn.setTarget_(self)
        self.fix_btn.setAction_("openAccessibility:")

        self.sep1 = self._sep()
        self.comfort_hdr = _label("Comfort level", size=15, bold=True)
        self.comfort_sub = _label("Pick how much help you want — change it anytime.",
                                  size=12, color=MUTED)

        selected = _which_preset(self.settings)
        for name in ("Mild", "Moderate", "Strong", "Off"):
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 38))
            btn.setButtonType_(NSRadioButton)
            btn.setTitle_(f"  {name}  —  {PRESET_INFO[name]}")
            btn.setFont_(NSFont.systemFontOfSize_(13))
            btn.setTarget_(self)
            btn.setAction_("radioChanged:")
            btn.setState_(NSOnState if name == selected else NSOffState)
            self._radios[name] = btn

        # Advanced disclosure.
        self.adv_toggle = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, INNER, 22))
        self.adv_toggle.setBezelStyle_(NSBezelStyleRegularSquare)
        self.adv_toggle.setBordered_(False)
        self.adv_toggle.setFont_(NSFont.systemFontOfSize_(12))
        self.adv_toggle.setTarget_(self)
        self.adv_toggle.setAction_("toggleAdvanced:")
        self.adv_toggle.setContentTintColor_(BLUE) if hasattr(self.adv_toggle, "setContentTintColor_") else None

        # Advanced controls.
        self._adv_views = []
        self.chk_smooth = self._check("Smooth mouse movement", 1, self.settings.smoothing_enabled)
        self.lbl_steady = _label("Steadiness   (very steady ◀ ▶ very responsive)", size=12, color=MUTED)
        self.sld_steady = self._slider(1, 0.2, 4.0, self.settings.min_cutoff)
        self.lbl_resp = _label("Fast-move snappiness", size=12, color=MUTED)
        self.sld_resp = self._slider(2, 0.002, 0.08, self.settings.beta)
        self.chk_key = self._check("Ignore accidental repeat key presses", 2, self.settings.debounce_enabled)
        self.lbl_key = _label("Key cooldown   (off ◀ ▶ long)", size=12, color=MUTED)
        self.sld_key = self._slider(3, 0.0, 200.0, self.settings.debounce_ms)
        self.chk_click = self._check("Ignore accidental double-clicks", 3, self.settings.click_debounce_enabled)
        self.lbl_click = _label("Click cooldown   (off ◀ ▶ long)", size=12, color=MUTED)
        self.sld_click = self._slider(4, 0.0, 300.0, self.settings.click_debounce_ms)
        self._adv_views = [
            self.chk_smooth, self.lbl_steady, self.sld_steady, self.lbl_resp, self.sld_resp,
            self.chk_key, self.lbl_key, self.sld_key, self.chk_click, self.lbl_click, self.sld_click,
        ]

        self.sep2 = self._sep()
        self.stats_lbl = _label("", size=12, color=MUTED)

        # Add everything to the content view.
        for v in ([self.title_lbl, self.sub_lbl, self.power_btn, self.status_lbl,
                   self.fix_btn, self.sep1, self.comfort_hdr, self.comfort_sub]
                  + list(self._radios.values())
                  + [self.adv_toggle] + self._adv_views + [self.sep2, self.stats_lbl]):
            self.content.addSubview_(v)

        self._refresh_power()
        self._relayout()

        # Status/stats refresh timer (main thread).
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

    # ---- layout -------------------------------------------------------------
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
            add(self.fix_btn, 32, gap_after=8)
        else:
            self.fix_btn.setHidden_(True)
        add(self.sep1, 1, gap_after=12)
        add(self.comfort_hdr, 22, gap_after=2)
        add(self.comfort_sub, 16, gap_after=8)
        for name in ("Mild", "Moderate", "Strong", "Off"):
            add(self._radios[name], 26, gap_after=4)
        top += 6
        self.adv_toggle.setTitle_(
            ("▾  Hide fine-tuning" if self._advanced_visible else "▸  Fine-tune (optional)")
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
            add(self.chk_key, 22, gap_after=4)
            add(self.lbl_key, 16, gap_after=0)
            add(self.sld_key, 20, gap_after=12)
            add(self.chk_click, 22, gap_after=4)
            add(self.lbl_click, 16, gap_after=0)
            add(self.sld_click, 20, gap_after=12)

        add(self.sep2, 1, gap_after=8)
        add(self.stats_lbl, 30, gap_after=0)

        total_h = top + M
        self.window.setContentSize_((W, total_h))
        for view, t, h, x, w in items:
            view.setFrame_(NSMakeRect(x, total_h - t - h, w, h))

    # ---- actions ------------------------------------------------------------
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
                config.apply_preset(self.settings, name)
                self._sync_advanced()
                self._save()
                break

    def openAccessibility_(self, sender):
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(ACCESS_URL))

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
        self._mark_custom()
        self._save_soon()

    @objc.python_method
    def _sync_advanced(self):
        self.chk_smooth.setState_(NSOnState if self.settings.smoothing_enabled else NSOffState)
        self.chk_key.setState_(NSOnState if self.settings.debounce_enabled else NSOffState)
        self.chk_click.setState_(NSOnState if self.settings.click_debounce_enabled else NSOffState)
        self.sld_steady.setFloatValue_(self.settings.min_cutoff)
        self.sld_resp.setFloatValue_(self.settings.beta)
        self.sld_key.setFloatValue_(self.settings.debounce_ms)
        self.sld_click.setFloatValue_(self.settings.click_debounce_ms)

    @objc.python_method
    def _mark_custom(self):
        # Highlight whichever preset (if any) the current settings now match.
        match = _which_preset(self.settings)
        for name, btn in self._radios.items():
            btn.setState_(NSOnState if name == match else NSOffState)

    # ---- timer / status -----------------------------------------------------
    def tick_(self, timer):
        msg = self._status_msg
        if msg.startswith("ACCESSIBILITY_REQUIRED"):
            self.status_lbl.setStringValue_(
                "⚠  One quick setup step — allow macOS permission below, then reopen."
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
        elif msg == "STOPPED":
            self.status_lbl.setStringValue_("○  Stopped.")
            self.status_lbl.setTextColor_(MUTED)
        else:
            self.status_lbl.setStringValue_(msg)
            self.status_lbl.setTextColor_(MUTED)

        e = self._engine
        self.stats_lbl.setStringValue_(
            f"Steadied {e.events_smoothed:,} movements · ignored "
            f"{e.keys_suppressed} shaky presses · {e.clicks_suppressed} stray clicks"
        )

    # ---- persistence / lifecycle -------------------------------------------
    _save_pending = False

    @objc.python_method
    def _save(self):
        config.save(self.settings)

    @objc.python_method
    def _save_soon(self):
        # Coalesce rapid slider drags into one save.
        if not self._save_pending:
            self._save_pending = True
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.4, self, "doSave:", None, False
            )

    def doSave_(self, timer):
        self._save_pending = False
        self._save()

    def windowWillClose_(self, notification):
        self._engine.stop()
        self._save()
        NSApplication.sharedApplication().terminate_(self)

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
