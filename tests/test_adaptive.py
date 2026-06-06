"""Tests for the Auto-mode adaptive controller (no Quartz needed)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tremor_assist.adaptive import AdaptiveController, recommend_preset  # noqa: E402

BASE = dict(base_cutoff=0.7, base_beta=0.015, base_deadzone=1.0)


def _an(freq, amp, conf):
    return {"freq_hz": freq, "amp_rms_px": amp, "confidence": conf, "band": "x"}


def test_low_confidence_falls_back_to_base():
    c = AdaptiveController()
    cutoff, beta, dz, gate = c.targets(_an(7.0, 4.0, 0.2), **BASE)
    assert gate == 0.0
    assert abs(cutoff - BASE["base_cutoff"]) < 1e-9
    assert abs(beta - BASE["base_beta"]) < 1e-9
    assert abs(dz - BASE["base_deadzone"]) < 1e-9


def test_no_frequency_falls_back_to_base():
    c = AdaptiveController()
    cutoff, beta, dz, gate = c.targets(_an(None, 0.0, 0.9), **BASE)
    assert gate == 0.0
    assert abs(cutoff - BASE["base_cutoff"]) < 1e-9


def test_higher_frequency_gives_higher_cutoff():
    """Constant-attenuation law: a faster tremor permits a higher (more
    responsive) cutoff than a slow one, at equal confidence."""
    c = AdaptiveController()
    low, *_ = c.targets(_an(4.0, 3.0, 0.9), **BASE)
    high, *_ = c.targets(_an(11.0, 3.0, 0.9), **BASE)
    assert high > low
    # And the slow tremor should pull below the base cutoff (smooth harder).
    assert low < BASE["base_cutoff"]


def test_cutoff_is_clamped():
    c = AdaptiveController(cutoff_min=0.3, cutoff_max=2.5)
    # Absurd frequency cannot push the cutoff past the ceiling.
    cutoff, *_ = c.targets(_an(100.0, 3.0, 1.0), **BASE)
    assert cutoff <= 2.5 + 1e-9


def test_amplitude_widens_deadzone():
    c = AdaptiveController()
    _, _, dz_small, _ = c.targets(_an(7.0, 1.0, 0.9), **BASE)
    _, _, dz_big, _ = c.targets(_an(7.0, 6.0, 0.9), **BASE)
    assert dz_big > dz_small
    assert dz_big >= BASE["base_deadzone"]


def test_deadzone_never_below_base():
    c = AdaptiveController()
    _, _, dz, _ = c.targets(_an(7.0, 0.1, 0.9), base_cutoff=0.7, base_beta=0.015, base_deadzone=2.0)
    assert dz >= 2.0 - 1e-9


def test_amplitude_lowers_beta():
    c = AdaptiveController()
    _, beta_small, _, _ = c.targets(_an(7.0, 1.0, 0.9), **BASE)
    _, beta_big, _, _ = c.targets(_an(7.0, 6.0, 0.9), **BASE)
    assert beta_big < beta_small
    assert beta_big >= c.beta_floor


def test_strength_increases_smoothing():
    c = AdaptiveController()
    gentle, *_ = c.targets(_an(8.0, 3.0, 0.9), strength=1.0, **BASE)
    aggressive, *_ = c.targets(_an(8.0, 3.0, 0.9), strength=2.5, **BASE)
    # More strength -> lower cutoff (smooths harder).
    assert aggressive < gentle


def test_update_glides_toward_target():
    c = AdaptiveController(tau=0.5)
    an = _an(5.0, 4.0, 0.9)
    target_cutoff, _, _, _ = c.targets(an, **BASE)
    cutoff = None
    prev_gap = None
    for _ in range(40):
        cutoff, _, _ = c.update(0.05, an, **BASE)
        gap = abs(cutoff - target_cutoff)
        if prev_gap is not None:
            assert gap <= prev_gap + 1e-9  # monotonically approaching
        prev_gap = gap
    assert abs(cutoff - target_cutoff) < 0.05  # converged


def test_reset_clears_state():
    c = AdaptiveController()
    c.update(0.1, _an(6.0, 4.0, 0.9), **BASE)
    assert c.state()["cutoff"] is not None
    c.reset()
    assert c.state()["cutoff"] is None
    assert c.gate == 0.0


def test_recommend_no_tremor():
    name, msg = recommend_preset(_an(None, 0.0, 0.1))
    assert name == "Mild"
    assert isinstance(msg, str) and msg


def test_recommend_strong_tremor_picks_auto():
    name, _ = recommend_preset(_an(6.0, 4.5, 0.9))
    assert name == "Auto"


def test_recommend_moderate_tremor():
    name, _ = recommend_preset(_an(7.0, 1.8, 0.9))
    assert name == "Strong"


def test_recommend_light_tremor():
    name, _ = recommend_preset(_an(9.0, 0.6, 0.9))
    assert name == "Moderate"


if __name__ == "__main__":
    for n, fn in sorted(globals().items()):
        if n.startswith("test_") and callable(fn):
            fn()
    print("all adaptive tests passed")
