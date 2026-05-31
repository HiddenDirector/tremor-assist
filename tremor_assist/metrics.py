from __future__ import annotations

import json
import os
import time

from .config import CONFIG_DIR

HISTORY_PATH = os.path.join(CONFIG_DIR, "history.json")
MAX_SESSIONS = 500


def load_history() -> list[dict]:
    try:
        with open(HISTORY_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError):
        return []


def record_session(snapshot: dict, *, min_movements: int = 5) -> dict | None:
    if snapshot.get("movements", 0) < min_movements:
        return None
    record = dict(snapshot)
    record["ended_at"] = time.time()
    history = load_history()
    history.append(record)
    if len(history) > MAX_SESSIONS:
        history = history[-MAX_SESSIONS:]
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = HISTORY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2)
    os.replace(tmp, HISTORY_PATH)
    return record


def all_time_totals(history: list[dict] | None = None) -> dict:
    if history is None:
        history = load_history()
    totals = {
        "sessions": len(history),
        "movements": 0,
        "jitter_removed_px": 0.0,
        "raw_path_px": 0.0,
        "keys_suppressed": 0,
        "clicks_suppressed": 0,
        "play_time_s": 0.0,
    }
    for s in history:
        totals["movements"] += s.get("movements", 0)
        totals["jitter_removed_px"] += s.get("jitter_removed_px", 0.0)
        totals["raw_path_px"] += s.get("raw_path_px", 0.0)
        totals["keys_suppressed"] += s.get("keys_suppressed", 0)
        totals["clicks_suppressed"] += s.get("clicks_suppressed", 0)
        totals["play_time_s"] += s.get("duration_s", 0.0)
    raw = totals["raw_path_px"]
    totals["jitter_removed_pct"] = (
        round(100.0 * totals["jitter_removed_px"] / raw, 1) if raw >= 1.0 else 0.0
    )
    return totals


def humanize_distance_px(px: float) -> str:
    # Rough: ~100 px ≈ 1 inch on a typical display.
    inches = px / 100.0
    if inches < 12:
        return f"{inches:.0f} in"
    feet = inches / 12.0
    if feet < 50:
        return f"{feet:.1f} ft"
    meters = inches * 0.0254
    return f"{meters:.0f} m"


def humanize_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"
