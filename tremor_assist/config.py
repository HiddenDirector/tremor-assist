from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

CONFIG_DIR = os.path.expanduser("~/.config/tremor-assist")
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")


@dataclass
class Settings:
    enabled: bool = True

    smoothing_enabled: bool = True
    min_cutoff: float = 1.0      # lower = more smoothing of slow movement
    beta: float = 0.02           # higher = less lag during fast flicks
    d_cutoff: float = 1.0

    deadzone_enabled: bool = True
    deadzone_px: float = 1.5     # hold cursor still within this radius

    debounce_enabled: bool = True
    debounce_ms: float = 60.0

    click_debounce_enabled: bool = True
    click_debounce_ms: float = 120.0

    click_lock_enabled: bool = True
    click_lock_ms: float = 120.0  # freeze the aim point this long around a click


PRESETS: dict[str, dict] = {
    "Off": dict(
        smoothing_enabled=False, deadzone_enabled=False,
        debounce_enabled=False, click_debounce_enabled=False, click_lock_enabled=False,
    ),
    "Mild": dict(
        smoothing_enabled=True, min_cutoff=2.0, beta=0.04,
        deadzone_enabled=True, deadzone_px=0.8,
        debounce_enabled=True, debounce_ms=40.0,
        click_debounce_enabled=True, click_debounce_ms=80.0,
        click_lock_enabled=True, click_lock_ms=80.0,
    ),
    "Moderate": dict(
        smoothing_enabled=True, min_cutoff=1.0, beta=0.02,
        deadzone_enabled=True, deadzone_px=1.5,
        debounce_enabled=True, debounce_ms=60.0,
        click_debounce_enabled=True, click_debounce_ms=120.0,
        click_lock_enabled=True, click_lock_ms=120.0,
    ),
    "Strong": dict(
        smoothing_enabled=True, min_cutoff=0.4, beta=0.008,
        deadzone_enabled=True, deadzone_px=3.0,
        debounce_enabled=True, debounce_ms=90.0,
        click_debounce_enabled=True, click_debounce_ms=180.0,
        click_lock_enabled=True, click_lock_ms=200.0,
    ),
}


def load() -> Settings:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        known = {f for f in Settings().__dataclass_fields__}  # type: ignore[attr-defined]
        return Settings(**{k: v for k, v in data.items() if k in known})
    except (FileNotFoundError, ValueError, TypeError):
        return Settings()


def save(settings: Settings) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(asdict(settings), fh, indent=2)
    os.replace(tmp, CONFIG_PATH)


def apply_preset(settings: Settings, name: str) -> Settings:
    for key, value in PRESETS.get(name, {}).items():
        setattr(settings, key, value)
    return settings
