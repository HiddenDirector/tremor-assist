# TremorAssist

[![CI](https://github.com/HiddenDirector/tremor-assist/actions/workflows/ci.yml/badge.svg)](https://github.com/HiddenDirector/tremor-assist/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

Steadies your mouse and keyboard system-wide so a shaky hand doesn't wreck your aim. macOS only, works in any game, no game mods.

## Why I made this

A family member has essential tremor and basically gave up on PC games — the crosshair wouldn't sit still, and single clicks kept registering as doubles. The accessibility settings built into macOS didn't really help for games.

So I built a little thing that sits between the hardware and whatever you're playing and quietly cleans up the input:

- **Aim stops shaking.** When your hand is mostly still, the cursor holds steady. When you actually move, it gets out of the way so it doesn't feel laggy.
- **No more accidental double-clicks** or a tap that fires twice.
- **The scroll wheel stops jumping** the wrong direction from a twitch.

It can also *watch* your tremor in real time and adjust itself, but you don't need to care about any of that to use it — just pick a comfort level and play.

## Getting started (the easy way)

1. Download/clone this folder.
2. Double-click **`TremorAssist.app`**.
3. macOS will ask for a permission the first time (see below). Grant it, reopen the app, done.

That's it. The window that pops up has big plain-language buttons — **Mild**, **Moderate**, **Strong**, **Auto**, **Off**. Start on **Moderate** and adjust from there.

### Prefer the terminal?

```bash
cd tremor-assist
./run.sh
```

First run makes a virtual environment and installs the (tiny) dependency list for you — give it a few seconds. After that it just launches.

## The one annoying part: permissions

macOS won't let *any* app touch your mouse/keyboard without permission. You'll need one or both of these under **System Settings → Privacy & Security**:

| Permission | What it unlocks | Where |
|---|---|---|
| **Accessibility** | Mouse smoothing | Privacy & Security → Accessibility |
| **Input Monitoring** | Key & click debounce | Privacy & Security → Input Monitoring |

They're independent — turn on just Accessibility and you still get mouse smoothing. The app tells you which one is active and has a button that jumps you straight to the right settings pane.

**Important:** after you flip a permission on, **quit and reopen the app**. macOS only picks up the change on a fresh launch. (This tripped me up more than once.)

## Picking a comfort level

Honestly, just try them:

- **Mild** – light touch, for a small shake.
- **Moderate** – good default. Start here.
- **Strong** – heavy smoothing if your hand shakes a lot.
- **Auto** – measures your tremor and sizes the help to match, live. Pick this if you're not sure.
- **Off** – passthrough, nothing changed.

If aiming still shakes → go toward **Strong**. If it feels sluggish → back toward **Mild**. Or just leave it on **Auto** and forget about it.

There's a **"Measure my tremor"** button too — it takes a 5-second reading and suggests a level for you.

## Running it without the window (headless)

If you just want it running in the background:

```bash
./run.sh --headless --preset Moderate
```

Prints live stats, `Ctrl+C` to stop.

## Building a real standalone .app

The `TremorAssist.app` in the repo root is a dev launcher (it reuses the project's venv). To make a self-contained app that runs on a clean Mac with no Terminal and no Python installed:

```bash
.venv/bin/python tools/make_icon.py     # regenerate the icon (optional)
.venv/bin/python setup.py py2app        # -> dist/TremorAssist.app
```

The shippable build lands in `dist/`. Drag it to `/Applications` and you're set.

## Native backend (C + Swift)

The filter math used to run in Python on every mouse event. That's the worst
possible place for it: each event crosses into the interpreter and takes the
GIL, which adds latency and — worse for gaming — *jitter*, so the smoothing
itself stutters. So the hot path now lives in compiled code:

- **`native/tremor_core.c`** — the One Euro Filter, hold-steady dead-zone, and
  scroll stabilizer in portable, dependency-free C. Same math as the Python
  version (there are parity tests asserting they agree to 1e-9), just compiled.
- **`native/tremor_engine.swift`** — a macOS `CGEventTap` engine that owns the
  tap and its run loop on a dedicated thread and calls the C core *inline*. On
  this path a mouse event is smoothed entirely in native code and **never enters
  Python**, so there's no GIL in the per-event loop at all.

Python still runs the Cocoa UI and pushes config down; it's just out of the
input path. The pure-Python implementation is kept as a fallback — if the native
libraries aren't built, everything still works, just slower.

Build the native libs:

```bash
./native/build.sh          # -> native/build/libtremorcore.dylib + libtremorengine.dylib
.venv/bin/python native/bench.py
```

The C core alone is ~2.5–3× faster than Python *through the ctypes boundary*;
the Swift tap removes that boundary too, so the real in-game path is faster
still. If the libs are absent, `one_euro.make_*` transparently returns the
Python versions.

## What's actually going on under the hood

Skip this unless you're curious — you don't need it to use the app.

The smoothing is a [One Euro Filter](https://gery.casiez.net/1euro/), which is the nice trick here: it smooths hard when you're moving slowly (killing tremor jitter) but barely touches fast deliberate flicks, so aiming doesn't lag. Key/click "debounce" just means a second press that lands suspiciously soon after the first gets treated as a bounce and dropped (real auto-repeat from *holding* a key still works).

The clever bit is the tremor measurement. Pathological tremor is roughly a sine wave in a narrow frequency band — Parkinsonian rest tremor around 3–6 Hz, essential/action tremor around 6–12 Hz — while deliberate aiming is slow, low-frequency motion. Because those live in different parts of the frequency spectrum, you can pull the tremor out of the cursor path with some DSP:

1. Buffer the last ~2s of pointer samples.
2. Resample to an even 120 Hz grid (a DFT needs even spacing).
3. Subtract the best-fit line per axis to drop the deliberate-movement part.
4. Hann window, then a direct DFT over 3–14 Hz.
5. Peak-pick with parabolic interpolation, plus a confidence score from how sharp the peak is.

`analysis.py` does all that with **zero NumPy/SciPy** — pure Python — so it's testable anywhere. **Auto** mode (`adaptive.py`) feeds that estimate back into the filter every event: faster tremor is easy to tell apart from intent so it stays responsive; slower tremor sits near intent so it smooths harder; a bigger shake widens the hold-steady zone. When the signal is weak it eases back to your manual settings instead of chasing noise.

## Project layout

```
tremor_assist/
  one_euro.py   One Euro Filter + dead-zone + scroll stabilizer (pure Python)
  analysis.py   DSP: detrend → resample → windowed DFT → tremor freq/amplitude
  adaptive.py   Auto controller: maps the live estimate back onto the filter
  engine.py     Quartz event tap — the actual mouse/key/scroll interception
  config.py     Settings, JSON save/load, the comfort presets
  ui.py         Native macOS (Cocoa) control panel
  __main__.py   GUI / headless entry point
TremorAssist.app   double-click launcher
tests/               unit tests for the filter, DSP, controller, config, etc.
```

The event tap runs on its own background thread with a CFRunLoop; the GUI keeps the main thread. The filter and DSP cores have no platform dependencies, which is why CI can test them on plain Linux runners.

## What it's good at (and not)

**Great for:** strategy, MOBA, point-and-click, top-down, card and turn-based games — anything that uses the system cursor.

**Hit or miss:** raw-input FPS games that read hardware mouse deltas directly and bypass the cursor. The tap smooths the delta fields too so it helps somewhat, but it's not a full fix yet. A virtual-HID driver for those is on the someday list.

**Not yet:** Windows. The core filter (`one_euro.py`) is portable; it just needs a Windows hook layer instead of the macOS event tap.

This measures tremor for **assistance, not diagnosis** — it's not a medical device.

## Running the tests

The filter and DSP are pure Python, so this works on any OS:

```bash
.venv/bin/python -m pip install pytest ruff
.venv/bin/python -m pytest        # 47 tests
.venv/bin/ruff check .
```

CI runs the same on Python 3.9–3.12 on every push.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, ship it. If it helps someone get back to gaming, that's the whole point.
