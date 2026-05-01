"""Tkinter control panel for the tremor-assist engine.

Runs on the main thread; the engine's event tap runs on its own thread. The UI
writes directly into the shared ``Settings`` object, so slider/preset changes
take effect live without restarting the tap.
"""

from __future__ import annotations

import subprocess
import tkinter as tk
from tkinter import ttk

from . import config
from .config import Settings
from .engine import TremorEngine


def _open_accessibility_pane() -> None:
    subprocess.run(
        [
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ],
        check=False,
    )


class ControlPanel:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = TremorEngine(settings, on_status=self._on_engine_status)

        self.root = tk.Tk()
        self.root.title("TremorAssist")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._status_var = tk.StringVar(value="Starting…")
        self._stats_var = tk.StringVar(value="")
        self._build()

        self.engine.start()
        self._poll_stats()

    # ----------------------------------------------------------------- UI build
    def _build(self) -> None:
        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(self.root, padding=12)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text="TremorAssist", font=("Helvetica", 16, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            frm,
            text="System-wide mouse smoothing + key/click debounce for hand tremor.",
            foreground="#555",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))

        # Master enable.
        self._enabled = tk.BooleanVar(value=self.settings.enabled)
        ttk.Checkbutton(
            frm, text="Assist enabled (master switch)", variable=self._enabled,
            command=self._on_enabled,
        ).grid(row=2, column=0, columnspan=3, sticky="w", **pad)

        # Presets.
        ttk.Label(frm, text="Preset:").grid(row=3, column=0, sticky="w", **pad)
        preset_frame = ttk.Frame(frm)
        preset_frame.grid(row=3, column=1, columnspan=2, sticky="w")
        for name in config.PRESETS:
            ttk.Button(
                preset_frame, text=name, width=8,
                command=lambda n=name: self._apply_preset(n),
            ).pack(side="left", padx=2)

        ttk.Separator(frm, orient="horizontal").grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=8
        )

        # Smoothing controls.
        self._smoothing = tk.BooleanVar(value=self.settings.smoothing_enabled)
        ttk.Checkbutton(
            frm, text="Mouse smoothing", variable=self._smoothing,
            command=self._on_smoothing,
        ).grid(row=5, column=0, columnspan=3, sticky="w", **pad)

        self._min_cutoff = self._make_slider(
            frm, 6, "Stability (less jitter ◀ ▶ more responsive)",
            0.2, 4.0, self.settings.min_cutoff, self._on_min_cutoff,
        )
        self._beta = self._make_slider(
            frm, 7, "Flick responsiveness", 0.002, 0.08,
            self.settings.beta, self._on_beta,
        )

        ttk.Separator(frm, orient="horizontal").grid(
            row=8, column=0, columnspan=3, sticky="ew", pady=8
        )

        # Debounce controls.
        self._debounce = tk.BooleanVar(value=self.settings.debounce_enabled)
        ttk.Checkbutton(
            frm, text="Keyboard debounce", variable=self._debounce,
            command=self._on_debounce,
        ).grid(row=9, column=0, columnspan=3, sticky="w", **pad)
        self._debounce_ms = self._make_slider(
            frm, 10, "Key debounce window (ms)", 0.0, 200.0,
            self.settings.debounce_ms, self._on_debounce_ms,
        )

        self._click_debounce = tk.BooleanVar(value=self.settings.click_debounce_enabled)
        ttk.Checkbutton(
            frm, text="Click debounce", variable=self._click_debounce,
            command=self._on_click_debounce,
        ).grid(row=11, column=0, columnspan=3, sticky="w", **pad)
        self._click_debounce_ms = self._make_slider(
            frm, 12, "Click debounce window (ms)", 0.0, 300.0,
            self.settings.click_debounce_ms, self._on_click_debounce_ms,
        )

        ttk.Separator(frm, orient="horizontal").grid(
            row=13, column=0, columnspan=3, sticky="ew", pady=8
        )

        ttk.Label(frm, textvariable=self._status_var, foreground="#0a7").grid(
            row=14, column=0, columnspan=3, sticky="w", **pad
        )
        ttk.Label(frm, textvariable=self._stats_var, foreground="#555").grid(
            row=15, column=0, columnspan=3, sticky="w", **pad
        )
        self._access_btn = ttk.Button(
            frm, text="Open Accessibility Settings", command=_open_accessibility_pane
        )  # shown only if permission is missing

    def _make_slider(self, parent, row, label, lo, hi, value, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10)
        var = tk.DoubleVar(value=value)
        scale = ttk.Scale(
            parent, from_=lo, to=hi, orient="horizontal", length=240, variable=var,
            command=lambda _v, c=command, vv=var: c(vv.get()),
        )
        scale.grid(row=row, column=1, sticky="w", padx=6, pady=2)
        val_lbl = ttk.Label(parent, width=6)
        val_lbl.grid(row=row, column=2, sticky="w")

        def refresh(*_):
            val_lbl.config(text=f"{var.get():.3g}")
        var.trace_add("write", refresh)
        refresh()
        return var

    # --------------------------------------------------------------- callbacks
    def _on_enabled(self):
        self.settings.enabled = self._enabled.get()
        self._save()

    def _on_smoothing(self):
        self.settings.smoothing_enabled = self._smoothing.get()
        self._save()

    def _on_debounce(self):
        self.settings.debounce_enabled = self._debounce.get()
        self._save()

    def _on_click_debounce(self):
        self.settings.click_debounce_enabled = self._click_debounce.get()
        self._save()

    def _on_min_cutoff(self, v):
        self.settings.min_cutoff = float(v)
        self._save_debounced()

    def _on_beta(self, v):
        self.settings.beta = float(v)
        self._save_debounced()

    def _on_debounce_ms(self, v):
        self.settings.debounce_ms = float(v)
        self._save_debounced()

    def _on_click_debounce_ms(self, v):
        self.settings.click_debounce_ms = float(v)
        self._save_debounced()

    def _apply_preset(self, name: str):
        config.apply_preset(self.settings, name)
        # Reflect into widgets.
        self._smoothing.set(self.settings.smoothing_enabled)
        self._debounce.set(self.settings.debounce_enabled)
        self._click_debounce.set(self.settings.click_debounce_enabled)
        self._min_cutoff.set(self.settings.min_cutoff)
        self._beta.set(self.settings.beta)
        self._debounce_ms.set(self.settings.debounce_ms)
        self._click_debounce_ms.set(self.settings.click_debounce_ms)
        self._save()

    # ------------------------------------------------------------------ plumbing
    def _on_engine_status(self, msg: str):
        # Called from the tap thread — marshal onto the Tk main loop.
        self.root.after(0, lambda: self._set_status(msg))

    def _set_status(self, msg: str):
        if msg.startswith("ACCESSIBILITY_REQUIRED"):
            self._status_var.set(
                "⚠ Accessibility permission needed. Click the button below, enable "
                "your terminal, then relaunch."
            )
            self._access_btn.grid(row=16, column=0, columnspan=3, pady=6)
        elif msg == "RUNNING":
            self._status_var.set("● Active — filtering input")
        elif msg == "STOPPED":
            self._status_var.set("○ Stopped")
        else:
            self._status_var.set(msg)

    def _poll_stats(self):
        e = self.engine
        self._stats_var.set(
            f"smoothed: {e.events_smoothed:,}   keys debounced: {e.keys_suppressed}"
            f"   clicks debounced: {e.clicks_suppressed}"
        )
        self.root.after(250, self._poll_stats)

    _save_job = None

    def _save_debounced(self):
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(400, self._save)

    def _save(self):
        config.save(self.settings)

    def _on_close(self):
        self.engine.stop()
        self._save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    settings = config.load()
    ControlPanel(settings).run()
