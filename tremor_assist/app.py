"""Application shell: menu bar item, app menu, About panel, lifecycle.

This turns the control panel into a real macOS app:
  * a menu-bar (status bar) item so it keeps protecting input while the window
    is closed and you're in a game;
  * a standard app menu with About and Quit (⌘Q);
  * closing the window hides to the menu bar instead of quitting;
  * the session is recorded to history on real quit.
"""

from __future__ import annotations

import os

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSOffState,
    NSOnState,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject

from . import __version__, config, metrics
from .ui import Controller

# Strong references to long-lived objects (see main()).
_KEEP_ALIVE: list = []


class AppDelegate(NSObject):
    def initWithController_(self, controller):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self.controller = controller
        self._preset_items = {}
        self._build_main_menu()
        self._build_status_item()
        return self

    # ---- main menu (⌘Q etc.) -----------------------------------------------
    @objc.python_method
    def _build_main_menu(self):
        menubar = NSMenu.alloc().init()
        app_item = NSMenuItem.alloc().init()
        menubar.addItem_(app_item)
        app_menu = NSMenu.alloc().initWithTitle_("TremorAssist")

        about = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "About TremorAssist", "showAbout:", "")
        about.setTarget_(self)
        app_menu.addItem_(about)
        app_menu.addItem_(NSMenuItem.separatorItem())

        show = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Show Control Panel", "showWindow:", "")
        show.setTarget_(self)
        app_menu.addItem_(show)
        app_menu.addItem_(NSMenuItem.separatorItem())

        hide = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Hide TremorAssist", "hide:", "h")
        app_menu.addItem_(hide)
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit TremorAssist", "terminate:", "q")
        app_menu.addItem_(quit_item)

        app_item.setSubmenu_(app_menu)
        NSApplication.sharedApplication().setMainMenu_(menubar)

    # ---- menu bar status item ----------------------------------------------
    @objc.python_method
    def _build_status_item(self):
        bar = NSStatusBar.systemStatusBar()
        self.status_item = bar.statusItemWithLength_(NSVariableStatusItemLength)
        button = self.status_item.button()
        img = None
        try:
            img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "waveform.path", "TremorAssist")
        except Exception:
            img = None
        if img is not None:
            img.setTemplate_(True)
            button.setImage_(img)
        else:
            button.setTitle_("〰")

        menu = NSMenu.alloc().init()
        menu.setDelegate_(self)  # menuNeedsUpdate_ refreshes dynamic state

        self._status_header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "TremorAssist", "", "")
        self._status_header.setEnabled_(False)
        menu.addItem_(self._status_header)
        menu.addItem_(NSMenuItem.separatorItem())

        self._toggle_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Protection On", "toggleProtection:", "")
        self._toggle_item.setTarget_(self)
        menu.addItem_(self._toggle_item)

        # Comfort presets submenu.
        presets_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Comfort level", "", "")
        presets_menu = NSMenu.alloc().init()
        for name in ("Mild", "Moderate", "Strong", "Off"):
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(name, "applyPreset:", "")
            it.setTarget_(self)
            it.setRepresentedObject_(name)
            presets_menu.addItem_(it)
            self._preset_items[name] = it
        presets_item.setSubmenu_(presets_menu)
        menu.addItem_(presets_item)
        menu.addItem_(NSMenuItem.separatorItem())

        show = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Control Panel…", "showWindow:", "")
        show.setTarget_(self)
        menu.addItem_(show)
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit TremorAssist", "terminate:", "q")
        menu.addItem_(quit_item)

        self.status_item.setMenu_(menu)

    # ---- dynamic menu refresh ----------------------------------------------
    def menuNeedsUpdate_(self, menu):
        s = self.controller.settings
        e = self.controller._engine
        running = e.is_running()
        if not s.enabled:
            state = "Off"
        elif running:
            state = "Active"
        else:
            state = "Needs permission"
        self._status_header.setTitle_(
            f"TremorAssist — {state}   ({e.jitter_removed_pct():.0f}% jitter removed)"
        )
        self._toggle_item.setTitle_("Turn Protection Off" if s.enabled else "Turn Protection On")
        self._toggle_item.setState_(NSOnState if s.enabled else NSOffState)
        current = self.controller._current_preset()
        for name, item in self._preset_items.items():
            item.setState_(NSOnState if name == current else NSOffState)

    # ---- actions ------------------------------------------------------------
    def showAbout_(self, sender):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        NSApplication.sharedApplication().orderFrontStandardAboutPanelWithOptions_({
            "ApplicationName": "TremorAssist",
            "ApplicationVersion": __version__,
            "Copyright": "Steadier gaming for hands that shake.",
            "Credits": _about_credits(),
        })

    def showWindow_(self, sender):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.controller.show()

    def toggleProtection_(self, sender):
        self.controller.togglePower_(sender)

    def applyPreset_(self, sender):
        self.controller.applyPresetNamed_(sender.representedObject())

    # ---- lifecycle ----------------------------------------------------------
    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return False  # keep running in the menu bar

    def applicationWillTerminate_(self, notification):
        e = self.controller._engine
        try:
            metrics.record_session(e.snapshot())
        except Exception:
            pass
        e.stop()
        config.save(self.controller.settings)


def _about_credits():
    from AppKit import NSAttributedString

    text = (
        "Smooths hand-tremor jitter from your mouse and debounces shaky key "
        "presses, system-wide, so games feel steady.\n\n"
        "Uses the One Euro Filter for adaptive smoothing."
    )
    return NSAttributedString.alloc().initWithString_(text)


def main():
    first_run = not os.path.exists(config.CONFIG_PATH)
    settings = config.load()

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    controller = Controller.alloc().initWithSettings_(settings)
    delegate = AppDelegate.alloc().initWithController_(controller)
    app.setDelegate_(delegate)
    # NSApplication's delegate is held weakly and NSApplication won't accept
    # arbitrary Python attributes, so keep strong refs in a module global to
    # stop the controller/delegate from being garbage-collected.
    _KEEP_ALIVE.extend([controller, delegate])

    controller.show()
    if first_run:
        from .ui import _show_welcome
        _show_welcome(controller)

    app.activateIgnoringOtherApps_(True)
    app.run()
