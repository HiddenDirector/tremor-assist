# TremorAssist

[![CI](https://github.com/usamehachasan67/tremor-assist/actions/workflows/ci.yml/badge.svg)](https://github.com/usamehachasan67/tremor-assist/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

**System-wide input smoothing — and live tremor analysis — for gamers with hand tremors (macOS).**

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
- **Scroll stabilization** — drops stray reverse scroll ticks so a shaking hand
  on the wheel doesn't make the page judder.

It also **measures your tremor in real time** — a dependency-free DSP pipeline
estimates the dominant tremor *frequency* (Hz) and amplitude from the live
cursor signal, and an **Auto** mode uses that estimate to size the assistance to
how much your hand is actually shaking, moment to moment.

Everything is tunable live, with presets from **Mild** to **Strong**, plus **Auto**.

---

## Features

- **One-click app** with its own icon — lives in the Dock *and* the menu bar.
- **Hold-steady dead-zone** — the cursor stays rock-solid while you're trying
  to hold still, then follows smoothly once you genuinely move (no lag).
- **Click stabilization** — freezes the aim point for a moment around each
  click so the tremor-jerk during the press doesn't pull your shot off target.
- **Tremor frequency analysis** — live estimate of your dominant tremor
  frequency (Hz) and amplitude, with a band label (rest-range 3–6 Hz vs
  action-range 6–12 Hz). Informational, not a diagnosis.
- **Auto-adapt mode** — sizes the hold-steady dead-zone to your *measured*
  tremor amplitude in real time, so help scales up and down as your hand does.
- **Scroll stabilization** — suppresses tremor-induced stray reverse scroll ticks.
- **Comfort levels** (Mild → Strong, plus Auto) in plain language; technical
  sliders are optional and hidden by default.
- **Menu-bar control** — toggle protection or switch comfort level without
  opening the window; closing the window keeps it running while you game.
- **Live tracking** — a real-time tremor graph, dominant-frequency readout,
  "% jitter removed", and per-session + all-time history.
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
| **Steady the scroll wheel** | Drops a small reverse scroll tick that lands just after scrolling the other way (a tremor twitch). |
| **Auto-adapt to my tremor** | Continuously widens the hold-steady dead-zone toward your measured tremor amplitude (never below your manual setting, capped for safety). |

Start on **Moderate**. If aiming still shakes, move toward **Strong** (or lower
Stability). If it feels laggy, raise Stability and Flick responsiveness. Not sure?
Pick **Auto** and let it follow your hand.

## How the tremor analysis works

Pathological tremor is a roughly sinusoidal oscillation in a narrow band —
Parkinsonian rest tremor sits around **3–6 Hz**, essential/action tremor around
**6–12 Hz** — whereas *deliberate* aiming is slow, low-frequency drift. That
separation in the frequency domain is what makes tremor measurable from the
cursor path alone. The pipeline in [`analysis.py`](tremor_assist/analysis.py) is
dependency-free (no NumPy/SciPy):

1. **Buffer** the last ~2 s of raw pointer samples (timestamped, irregularly
   sampled as mouse events arrive).
2. **Resample** onto a uniform 120 Hz grid by linear interpolation, since a DFT
   assumes even spacing.
3. **Detrend** each axis by subtracting its least-squares line — this removes the
   deliberate movement component, leaving only the oscillation.
4. **Window** (Hann) to suppress spectral leakage, then evaluate a **direct DFT**
   over a 3–14 Hz grid and combine the two axes' power spectra.
5. **Peak-pick** the spectrum with parabolic interpolation for sub-bin frequency
   resolution, and compute a **confidence** score from how concentrated the
   spectrum is around that peak (a clean sinusoid spikes; broadband noise spreads).

The result drives the on-screen readout and, in **Auto** mode, a closed-loop
controller. The whole module is covered by unit tests that feed synthetic,
unevenly-sampled sinusoids (with and without deliberate drift) and assert the
recovered frequency, amplitude, and confidence.

### Auto mode: a closed-loop adaptive controller

Rather than a single fixed setting, **Auto** ([`adaptive.py`](tremor_assist/adaptive.py))
retunes the filter from the live estimate every event:

- **Frequency → smoothing cutoff.** A first-order low-pass attenuates a
  frequency `f` by roughly `cutoff / f`, so holding a *constant* tremor
  attenuation means setting `min_cutoff = ratio · f_tremor`. A fast tremor
  (10 Hz) is easy to separate from intentional motion (<2 Hz), so the cutoff
  rises and you stay responsive; a slow tremor (4 Hz) sits near intent, so the
  cutoff drops and it smooths harder.
- **Amplitude → dead-zone + beta.** A bigger shake widens the hold-steady zone
  and lowers `beta`, so a violent tremor jerk isn't mistaken for a deliberate flick.
- **Confidence gating + time-constant glide.** When the tremor signal is weak or
  absent, the controller blends back to your base settings instead of chasing
  noise, and all changes ease in smoothly so nothing snaps.

The control panel shows what Auto is doing live (effective cutoff, hold-zone, and
how strongly it's engaged), and **"Measure my tremor"** runs a 5-second reading
that recommends a comfort level for you.

## Architecture

```
tremor_assist/
  one_euro.py   Pure-Python One Euro Filter + dead-zone + scroll stabilizer
                (unit-tested, no platform deps)
  analysis.py   Dependency-free DSP: detrend → resample → windowed DFT →
                dominant tremor frequency / amplitude / confidence
  adaptive.py   Closed-loop Auto controller: frequency→cutoff, amplitude→
                dead-zone/beta, confidence-gated, time-constant glide
  engine.py     Quartz CGEventTap: smooths motion, debounces keys/clicks,
                stabilizes scroll, feeds the analyzer, drives Auto adaptation
  config.py     Settings dataclass, JSON persistence, presets (incl. Auto)
  ui.py         Native macOS (Cocoa/AppKit) control panel — comfort levels,
                live frequency readout, Auto status, "measure my tremor"
  __main__.py   GUI / headless entry point
TremorAssist.app  Double-clickable launcher bundle
tests/
  test_one_euro.py   filter, dead-zone behavior
  test_analysis.py   frequency/amplitude recovery from synthetic tremor
  test_adaptive.py   Auto control law + preset recommendation
  test_scroll.py     scroll-reversal suppression
  test_config.py     settings persistence + presets
  test_metrics.py    session history aggregation
```

The event tap runs on a background thread with its own CFRunLoop; the GUI owns
the main thread. The callback only reads a shared `Settings` object, so changes
apply instantly. The signal-processing and filter cores have **zero platform
dependencies**, so they're tested on every push via CI without needing macOS at
the GUI layer.

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

The filter and DSP cores are pure Python, so the suite runs on any platform:

```bash
.venv/bin/python -m pip install pytest ruff
.venv/bin/python -m pytest        # 47 tests
.venv/bin/ruff check .            # lint
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the same on
Python 3.9–3.12 on every push.

## License

MIT — see [LICENSE](LICENSE).
