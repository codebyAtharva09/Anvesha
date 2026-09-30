"""Mobile-platform motion and the virtual pan/tilt gimbal.

Platform motion rotates the terminal's base, so it shifts the camera line of
sight (LOS) exactly like a pointing error. It is expressed in screen pixels
(1 px = deg_per_px degrees). PS26169 allows up to +/-20 px/frame, with linear
motion mandatory and circular / random / spiral / figure-8 optional.

The gimbal is modelled as a rate-commanded two-axis mount with:
  * actuator (command) latency,
  * first-order rate-loop lag,
  * acceleration limit and rate saturation (PS #13/#14: 5-10 deg/s),
  * mechanical travel limits.
"""
from __future__ import annotations

import collections
import math
from typing import Deque, Tuple

import numpy as np


class PlatformMotion:
    def __init__(self, kind: str, amp_px_per_frame: float, frame_rate: float, period_s: float,
                 vib_hz, rng: np.random.Generator):
        self.kind = kind
        self.v = amp_px_per_frame * frame_rate          # px/s peak LOS rate
        self.amp = amp_px_per_frame
        self.P = max(period_s, 0.5)
        self.vib_hz = list(vib_hz or [])
        self.rng = rng
        self.t = 0.0
        self.offset = np.zeros(2)       # LOS offset (px)
        self.rate = np.zeros(2)         # LOS rate (px/s)
        ang = rng.uniform(0, 2 * math.pi)
        self.dir = np.array([math.cos(ang), math.sin(ang)])
        self._ou = np.zeros(2)
        self._vib_phase = rng.uniform(0, 2 * math.pi, size=(max(len(self.vib_hz), 1), 2))

    def _rate(self, t: float) -> np.ndarray:
        k, v, P = self.kind, self.v, self.P
        if k == "none" or v == 0 and k != "vibration":
            return np.zeros(2)
        if k == "linear":
            # constant-rate drift that reverses every half period (keeps the
            # gimbal inside its travel while remaining piece-wise linear)
            s = 1.0 if (t % P) < P / 2 else -1.0
            return v * s * self.dir
        if k == "circular":
            w = 2 * math.pi / P
            return v * np.array([-math.sin(w * t), math.cos(w * t)])
        if k == "figure8":
            w = 2 * math.pi / P
            return v * np.array([math.cos(w * t), math.cos(2 * w * t)])
        if k == "spiral":
            w = 2 * math.pi / P
            g = 0.5 + 0.5 * math.sin(2 * math.pi * t / (4 * P))
            return v * g * np.array([-math.sin(w * t), math.cos(w * t)])
        if k == "random":
            return self._ou * v
        return np.zeros(2)

    def step(self, dt: float) -> None:
        self.t += dt
        if self.kind == "random":
            tau = 0.8
            self._ou += (-self._ou / tau) * dt + math.sqrt(2 * dt / tau) * self.rng.standard_normal(2) * 0.6
            self._ou = np.clip(self._ou, -1, 1)
        if self.kind == "vibration":
            # band-limited vibration: sum of sinusoids, displacement amplitude = amp px
            off = np.zeros(2)
            rate = np.zeros(2)
            n = max(len(self.vib_hz), 1)
            for i, f in enumerate(self.vib_hz):
                w = 2 * math.pi * f
                ph = self._vib_phase[i]
                off += (self.amp / n) * np.sin(w * self.t + ph)
                rate += (self.amp / n) * w * np.cos(w * self.t + ph)
            self.rate = rate
            self.offset = off
            return
        self.rate = self._rate(self.t)
        self.offset = self.offset + self.rate * dt


class IMU:
    """Rate gyro on the platform: measures platform LOS rate with noise + bias."""

    def __init__(self, noise: float, bias: float, rng: np.random.Generator):
        self.noise, self.rng = noise, rng
        self.bias = bias * rng.standard_normal(2)

    def read(self, true_rate: np.ndarray) -> np.ndarray:
        return true_rate + self.bias + self.noise * self.rng.standard_normal(2)


class Gimbal:
    """Rate-commanded two-axis gimbal. Angles/rates in *screen pixels* (and px/s);
    conversion to degrees is done by the caller with deg_per_px."""

    def __init__(self, max_rate_px: Tuple[float, float], max_acc_px: float, tau: float,
                 latency: float, limit_px: Tuple[float, float], sim_dt: float):
        self.max_rate = np.array(max_rate_px, dtype=float)
        self.max_acc = float(max_acc_px)
        self.tau = max(tau, 1e-4)
        self.limit = np.array(limit_px, dtype=float)
        self.angle = np.zeros(2)
        self.rate = np.zeros(2)
        self.cmd = np.zeros(2)
        n = max(int(round(latency / sim_dt)), 0)
        self.queue: Deque[np.ndarray] = collections.deque([np.zeros(2)] * n)
        self.saturated = np.zeros(2, dtype=bool)

    def command(self, rate_cmd: np.ndarray) -> None:
        self.cmd = np.asarray(rate_cmd, dtype=float)

    def step(self, dt: float) -> None:
        self.queue.append(self.cmd.copy())
        cmd = self.queue.popleft()
        cmd_sat = np.clip(cmd, -self.max_rate, self.max_rate)
        self.saturated = np.abs(cmd) > self.max_rate + 1e-9
        # first-order rate loop with acceleration limit
        acc = (cmd_sat - self.rate) / self.tau
        acc = np.clip(acc, -self.max_acc, self.max_acc)
        self.rate = np.clip(self.rate + acc * dt, -self.max_rate, self.max_rate)
        self.angle = self.angle + self.rate * dt
        hit = np.abs(self.angle) > self.limit
        if hit.any():
            self.angle = np.clip(self.angle, -self.limit, self.limit)
            self.rate[hit] = 0.0
