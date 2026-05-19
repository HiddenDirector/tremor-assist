"""Entry point: ``python -m tremor_assist [--headless] [--preset NAME]``."""

from __future__ import annotations

import argparse
import sys
import time

from . import config, metrics
from .engine import TremorEngine


def _run_headless(preset: str | None) -> int:
    settings = config.load()
    if preset:
        config.apply_preset(settings, preset)
    status = {"msg": ""}
    engine = TremorEngine(settings, on_status=lambda m: status.update(msg=m))
    engine.start()
    time.sleep(0.5)
    if status["msg"].startswith("ACCESSIBILITY_REQUIRED"):
        print(
            "ERROR: Accessibility permission required.\n"
            "Grant it to your terminal under System Settings > Privacy & Security "
            "> Accessibility, then rerun.",
            file=sys.stderr,
        )
        return 2
    print("TremorAssist running (headless). Press Ctrl+C to stop.")
    print(f"  smoothing={settings.smoothing_enabled} "
          f"min_cutoff={settings.min_cutoff} beta={settings.beta}")
    try:
        while True:
            time.sleep(1.0)
            print(
                f"\rmovements={engine.events_smoothed:,} "
                f"jitter_removed={engine.jitter_removed_pct():.0f}% "
                f"tremor_now={engine.avg_tremor_px():.1f}px "
                f"keys_debounced={engine.keys_suppressed} "
                f"clicks_debounced={engine.clicks_suppressed}   ",
                end="",
                flush=True,
            )
    except KeyboardInterrupt:
        print("\nStopping…")
        engine.stop()
        rec = metrics.record_session(engine.snapshot())
        if rec:
            print(f"Session saved: {rec['movements']:,} movements, "
                  f"{rec['jitter_removed_pct']:.0f}% jitter removed.")
        totals = metrics.all_time_totals()
        print(f"All time: {totals['movements']:,} movements over "
              f"{totals['sessions']} sessions, "
              f"{metrics.humanize_distance_px(totals['jitter_removed_px'])} of shake removed.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="tremor_assist", description=__doc__)
    parser.add_argument("--headless", action="store_true", help="run without the GUI")
    parser.add_argument("--preset", choices=list(config.PRESETS), help="apply a preset on start")
    args = parser.parse_args()

    if args.headless:
        return _run_headless(args.preset)

    if args.preset:
        settings = config.load()
        config.apply_preset(settings, args.preset)
        config.save(settings)
    from .app import main as app_main
    app_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
