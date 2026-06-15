
from __future__ import annotations

import math


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _smoothstep(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 1.0 if x >= hi else 0.0
    t = _clamp((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _glide(current: float | None, target: float, alpha: float) -> float:
    if current is None:
        return target
    return current + alpha * (target - current)


class AdaptiveController:

    def __init__(
        self,
        *,
        tau: float = 0.6,
        conf_lo: float = 0.4,
        conf_hi: float = 0.8,
        cutoff_ratio: float = 0.12,
        cutoff_min: float = 0.3,
        cutoff_max: float = 2.5,
        deadzone_max: float = 8.0,
        beta_floor: float = 0.004,
        beta_amp_k: float = 0.18,
    ) -> None:
        self.tau = float(tau)
        self.conf_lo = float(conf_lo)
        self.conf_hi = float(conf_hi)
        self.cutoff_ratio = float(cutoff_ratio)
        self.cutoff_min = float(cutoff_min)
        self.cutoff_max = float(cutoff_max)
        self.deadzone_max = float(deadzone_max)
        self.beta_floor = float(beta_floor)
        self.beta_amp_k = float(beta_amp_k)
        self._cutoff: float | None = None
        self._beta: float | None = None
        self._deadzone: float | None = None
        self.gate = 0.0

    def reset(self) -> None:
        self._cutoff = None
        self._beta = None
        self._deadzone = None
        self.gate = 0.0

    def targets(
        self,
        analysis: dict,
        base_cutoff: float,
        base_beta: float,
        base_deadzone: float,
        strength: float = 1.0,
    ) -> tuple[float, float, float, float]:
        conf = float(analysis.get("confidence", 0.0) or 0.0)
        freq = analysis.get("freq_hz")
        amp = float(analysis.get("amp_rms_px", 0.0) or 0.0)
        strength = _clamp(strength, 0.0, 3.0)

        gate = _smoothstep(conf, self.conf_lo, self.conf_hi) if freq else 0.0

        if freq:
            s = max(0.5, strength)
            cutoff_t = _clamp(freq * self.cutoff_ratio / s, self.cutoff_min, self.cutoff_max)
        else:
            cutoff_t = base_cutoff

        dz_t = _clamp(max(base_deadzone, amp * strength), 0.0, self.deadzone_max)
        beta_t = max(self.beta_floor, base_beta / (1.0 + self.beta_amp_k * amp * strength))

        cutoff = _lerp(base_cutoff, cutoff_t, gate)
        beta = _lerp(base_beta, beta_t, gate)
        deadzone = _lerp(base_deadzone, dz_t, gate)
        return cutoff, beta, deadzone, gate

    def update(
        self,
        dt: float,
        analysis: dict,
        base_cutoff: float,
        base_beta: float,
        base_deadzone: float,
        strength: float = 1.0,
    ) -> tuple[float, float, float]:
        cutoff, beta, deadzone, gate = self.targets(
            analysis, base_cutoff, base_beta, base_deadzone, strength
        )
        self.gate = gate
        a = 1.0 - math.exp(-max(0.0, dt) / self.tau) if self.tau > 0 else 1.0
        self._cutoff = _glide(self._cutoff, cutoff, a)
        self._beta = _glide(self._beta, beta, a)
        self._deadzone = _glide(self._deadzone, deadzone, a)
        return self._cutoff, self._beta, self._deadzone

    def state(self) -> dict:
        return {
            "cutoff": self._cutoff,
            "beta": self._beta,
            "deadzone": self._deadzone,
            "gate": self.gate,
        }


def recommend_preset(analysis: dict) -> tuple[str, str]:
    conf = float(analysis.get("confidence", 0.0) or 0.0)
    freq = analysis.get("freq_hz")
    amp = float(analysis.get("amp_rms_px", 0.0) or 0.0)

    if not freq or conf < 0.4:
        return "Mild", "No strong tremor detected — a light touch should feel best."
    if amp >= 3.0:
        return "Auto", (
            f"A clear ~{freq:.0f} Hz tremor of about {amp:.1f} px — "
            "Auto will track it as it changes."
        )
    if amp >= 1.2:
        return "Strong", (
            f"A steady ~{freq:.0f} Hz tremor around {amp:.1f} px — "
            "Strong gives you the most steadiness."
        )
    return "Moderate", (
        f"A light ~{freq:.0f} Hz tremor ({amp:.1f} px) — "
        "Moderate keeps things responsive."
    )
