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

## Requirements

- macOS
- Python 3.9+
- **Accessibility permission** for the app that launches it (Terminal, iTerm,
  etc.). This is required for any tool that reads/alters input system-wide.

## Quick start

```bash
cd tremor-assist
./run.sh
```

`run.sh` creates a virtual environment, installs dependencies, and launches the
control panel. On first launch macOS will block the event tap until you grant
Accessibility permission:

> **System Settings → Privacy & Security → Accessibility** → enable your
> terminal app → relaunch.

The app shows a button that opens this pane directly if permission is missing.

### Headless mode (no GUI)

```bash
./run.sh --headless --preset Moderate
```

Runs the filter with a chosen preset and prints live stats. Ctrl+C to stop.

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
  ui.py         Tkinter control panel (live tuning + stats)
  __main__.py   GUI / headless entry point
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
