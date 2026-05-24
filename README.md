# TremorAssist

**System-wide input smoothing for gamers with hand tremors (macOS).**

Hand tremor (essential tremor, Parkinson's, post-stroke, fatigue, etc.) makes
PC gaming hard in two specific ways:

1. **Aiming jitter** — the cursor/crosshair shakes because the hand shakes.
2. **Bounced inputs** — one intended key press or click registers as several.

TremorAssist sits between your input devices and your games and fixes both,
without modifying any game:

- **Adaptive mouse smoothing** using the [One Euro Filter](https://gery.casiez.net/1euro/).
  It erases tremor jitter when your hand is nearly still, yet opens up during
  fast deliberate flicks so aiming doesn't feel laggy.
- **Keyboard debounce** — ignores a repeat key-down that lands within a short
  window of the previous one (auto-repeat from *holding* a key is preserved).
- **Click debounce** — prevents tremor-induced accidental double-clicks/misfires.

Everything is tunable live, with presets from **Mild** to **Strong**.

---

## Features

- **One-click app** with its own icon — lives in the Dock *and* the menu bar.
- **Hold-steady dead-zone** — the cursor stays rock-solid while you're trying
  to hold still, then follows smoothly once you genuinely move (no lag).
- **Click stabilization** — freezes the aim point for a moment around each
  click so the tremor-jerk during the press doesn't pull your shot off target.
- **Comfort levels** (Mild → Strong) in plain language; technical sliders are
  optional and hidden by default.
- **Menu-bar control** — toggle protection or switch comfort level without
  opening the window; closing the window keeps it running while you game.
- **Live tracking** — a real-time tremor graph, "% jitter removed", and
  per-session + all-time history.
- **One Euro Filter** smoothing plus keyboard/click debounce, system-wide.

## Requirements

- macOS
- Python 3.9+ (only to build/run from source)
- **Two macOS permissions** for the app (System Settings ▸ Privacy & Security):
  - **Accessibility** → required for **mouse smoothing**.
  - **Input Monitoring** → required for **keyboard/click debounce**.

  The two are independent: with only Accessibility you still get mouse
  smoothing; the app tells you which is active and gives a button for each.
  After toggling a permission on, **reopen the app**.

## Quick start

**The easy way:** double-click **`TremorAssist.app`** in Finder. The first
launch sets itself up automatically (this takes a moment), then the control
panel opens with a short welcome.

**From the terminal** (equivalent):

```bash
cd tremor-assist
./run.sh
```

Either way, a virtual environment is created, dependencies are installed, and
the native control panel opens. On first launch macOS will block the event tap
until you grant Accessibility permission:

> **System Settings → Privacy & Security → Accessibility** → enable your
> terminal app → relaunch.

The app shows a button that opens this pane directly if permission is missing.

### Headless mode (no GUI)

```bash
./run.sh --headless --preset Moderate
```

Runs the filter with a chosen preset and prints live stats. Ctrl+C to stop.

## Building a standalone app

To produce a self-contained `TremorAssist.app` that bundles its own Python and
runs on a clean Mac (drop it in `/Applications`, no Terminal needed):

```bash
.venv/bin/python tools/make_icon.py     # (re)generate the icon, optional
.venv/bin/python setup.py py2app        # standalone build -> dist/TremorAssist.app
```

The result is in `dist/`. The lightweight `TremorAssist.app` checked into the
repo root is the developer launcher (it reuses the project's virtualenv); the
`dist/` build is the shippable one.

## How to tune it

| Control | What it does |
|---|---|
| **Stability** (`min_cutoff`) | Lower = more jitter removed at low speed (more lag). Higher = more responsive. |
| **Flick responsiveness** (`beta`) | Higher = the filter relaxes faster during quick movements, reducing lag on flicks. |
| **Key debounce window** | A second press of the same key within this many ms is treated as a bounce and dropped. |
| **Click debounce window** | Same idea for mouse buttons. |

Start on **Moderate**. If aiming still shakes, move toward **Strong** (or lower
Stability). If it feels laggy, raise Stability and Flick responsiveness.

## Architecture

```
tremor_assist/
  one_euro.py   Pure-Python One Euro Filter (unit-tested, no platform deps)
  engine.py     Quartz CGEventTap: smooths motion, debounces keys/clicks
  config.py     Settings dataclass, JSON persistence, presets
  ui.py         Native macOS (Cocoa/AppKit) control panel — comfort levels,
                big on/off button, optional fine-tuning, live stats
  __main__.py   GUI / headless entry point
TremorAssist.app  Double-clickable launcher bundle
tests/
  test_one_euro.py
```

The event tap runs on a background thread with its own CFRunLoop; the GUI owns
the main thread. The callback only reads a shared `Settings` object, so changes
apply instantly.

## Scope & limitations

- **Cursor-based games work best.** Strategy, MOBA, point-and-click, top-down,
  card and turn-based games benefit directly from absolute-position smoothing.
- **Raw-input FPS games** (which read hardware mouse deltas directly, bypassing
  the system cursor) may not be fully affected. The tap smooths the system-level
  delta fields too, which helps, but a future release may add a virtual-HID
  driver for those titles.
- macOS only for now (built on Quartz event taps). A Windows port would use a
  low-level mouse/keyboard hook with the same `one_euro.py` core.

## Tests

```bash
.venv/bin/python tests/test_one_euro.py
```

## License

MIT — see [LICENSE](LICENSE).
