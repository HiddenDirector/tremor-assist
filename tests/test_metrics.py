"""Tests for session tracking / history aggregation (no Quartz needed)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tremor_assist import metrics  # noqa: E402


def _isolate(tmpdir):
    metrics.HISTORY_PATH = os.path.join(tmpdir, "history.json")


def test_skips_trivial_sessions():
    with tempfile.TemporaryDirectory() as d:
        _isolate(d)
        assert metrics.record_session({"movements": 2}) is None
        assert metrics.load_history() == []


def test_records_and_aggregates():
    with tempfile.TemporaryDirectory() as d:
        _isolate(d)
        metrics.record_session({
            "movements": 1000, "raw_path_px": 5000.0, "jitter_removed_px": 1500.0,
            "keys_suppressed": 4, "clicks_suppressed": 1, "duration_s": 600.0,
        })
        metrics.record_session({
            "movements": 500, "raw_path_px": 2000.0, "jitter_removed_px": 500.0,
            "keys_suppressed": 2, "clicks_suppressed": 0, "duration_s": 300.0,
        })
        t = metrics.all_time_totals()
        assert t["sessions"] == 2
        assert t["movements"] == 1500
        assert t["jitter_removed_px"] == 2000.0
        assert t["keys_suppressed"] == 6
        # 2000 removed out of 7000 raw -> ~28.6%
        assert 28.0 <= t["jitter_removed_pct"] <= 29.0


def test_history_is_bounded():
    with tempfile.TemporaryDirectory() as d:
        _isolate(d)
        metrics.MAX_SESSIONS = 10
        for i in range(25):
            metrics.record_session({"movements": 100 + i})
        assert len(metrics.load_history()) == 10


def test_humanize():
    assert metrics.humanize_distance_px(50) == "0 in"
    assert metrics.humanize_distance_px(600).endswith("in")
    assert metrics.humanize_distance_px(5000).endswith("ft")
    assert metrics.humanize_duration(0) == "0s"
    assert metrics.humanize_duration(125) == "2m 5s"
    assert metrics.humanize_duration(3725) == "1h 2m"


if __name__ == "__main__":
    test_skips_trivial_sessions()
    test_records_and_aggregates()
    test_history_is_bounded()
    test_humanize()
    print("all metrics tests passed")
