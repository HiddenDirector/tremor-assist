"""Tests for settings persistence and presets (no Quartz needed)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tremor_assist import config  # noqa: E402
from tremor_assist.config import Settings  # noqa: E402


def test_roundtrip_save_load(monkeypatch=None):
    with tempfile.TemporaryDirectory() as d:
        config.CONFIG_PATH = os.path.join(d, "settings.json")
        config.CONFIG_DIR = d
        s = Settings()
        s.min_cutoff = 0.33
        s.auto_adapt_enabled = True
        config.save(s)
        loaded = config.load()
        assert abs(loaded.min_cutoff - 0.33) < 1e-9
        assert loaded.auto_adapt_enabled is True


def test_unknown_keys_ignored():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "settings.json")
        config.CONFIG_PATH = path
        config.CONFIG_DIR = d
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"min_cutoff": 1.5, "bogus_legacy_field": 99}')
        loaded = config.load()  # must not raise
        assert abs(loaded.min_cutoff - 1.5) < 1e-9


def test_every_preset_applies_cleanly():
    for name in config.PRESETS:
        s = config.apply_preset(Settings(), name)
        assert isinstance(s, Settings)


def test_auto_preset_enables_adaptation():
    s = config.apply_preset(Settings(), "Auto")
    assert s.auto_adapt_enabled is True
    assert s.scroll_stabilize_enabled is True


def test_off_preset_disables_everything():
    s = config.apply_preset(Settings(), "Off")
    assert not s.smoothing_enabled
    assert not s.deadzone_enabled
    assert not s.scroll_stabilize_enabled
    assert not s.auto_adapt_enabled


if __name__ == "__main__":
    for n, fn in sorted(globals().items()):
        if n.startswith("test_") and callable(fn):
            fn()
    print("all config tests passed")
