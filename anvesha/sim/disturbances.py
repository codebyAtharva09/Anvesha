"""Disturbance engine: atmosphere, turbulence, camera jitter and sensor noise.

Order of application inside one exposure (physically motivated):
  1. atmosphere  - transmission loss on the beacon, additive air-light veil,
                   forward-scatter blur (fog), rain streaks, low-light gain
  2. turbulence  - beacon scintillation (log-normal intensity, AR(1) in time)
                   and angle-of-arrival wander (beacon image motion)
  3. sensor      - Poisson shot noise, Gaussian read noise, 8-bit quantisation
  4. impulsive   - salt & pepper (dead/hot pixels, transmission errors)
Camera jitter is applied to the line of sight before rendering (see world.py).

All random draws come from dedicated, seeded generators -> reproducible.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np

from ..config import AtmosphereCfg, NoiseCfg


@dataclass
class AtmosState:
    transmission: float = 1.0     # multiplicative loss on the beacon signal
    airlight: float = 0.0         # additive veil (DN)
    blur_sigma: float = 0.0       # extra forward-scatter blur on the beacon (px)
    gain: float = 1.0             # global exposure/illumination gain (low light)
    rain_streaks: int = 0


def atmosphere_state(cfg: AtmosphereCfg) -> AtmosState:
    s = float(np.clip(cfg.severity, 0.0, 1.0))
    c = cfg.condition
    if c == "haze":
        return AtmosState(transmission=1 - 0.55 * s, airlight=45 * s, blur_sigma=0.4 * s)
    if c == "fog":
        return AtmosState(transmission=1 - 0.8 * s, airlight=90 * s, blur_sigma=0.8 + 2.2 * s)
    if c == "rain":
        return AtmosState(transmission=1 - 0.35 * s, airlight=20 * s, blur_sigma=0.3 * s,
                          rain_streaks=int(30 + 170 * s))
    if c == "low_light":
        return AtmosState(transmission=1.0, airlight=0.0, gain=1 - 0.85 * s)
    return AtmosState()


class Disturbances:
    def __init__(self, noise: NoiseCfg, atm: AtmosphereCfg, rng_img: np.random.Generator,
                 rng_turb: np.random.Generator, rng_jit: np.random.Generator):
        self.noise, self.atm_cfg = noise, atm
        self.rng, self.rt, self.rj = rng_img, rng_turb, rng_jit
        self.atm = atmosphere_state(atm)
        self._scint = 0.0
        self._aoa = np.zeros(2)
        self._jit_t = 0
        self._jit_phase = rng_jit.uniform(0, 2 * math.pi, 2)
        self._veil = None

    def reconfigure(self, noise: NoiseCfg, atm: AtmosphereCfg) -> None:
        self.noise, self.atm_cfg = noise, atm
        self.atm = atmosphere_state(atm)
        self._veil = None

    # ---------------- line-of-sight disturbances ------------------------ #
    def jitter(self) -> np.ndarray:
        a = self.noise.jitter_px
        self._jit_t += 1
        if a <= 0:
            return np.zeros(2)
        m = self.noise.jitter_mode
        if m == "gaussian":
            return np.clip(self.rj.normal(0, a / 2.0, 2), -a, a)
        if m == "sinusoidal":
            f = np.array([0.23, 0.31])  # cycles per frame (aliased vibration)
            return a * np.sin(2 * math.pi * f * self._jit_t + self._jit_phase)
        return self.rj.uniform(-a, a, 2)

    def turbulence(self) -> Tuple[float, np.ndarray]:
        """Returns (intensity factor, angle-of-arrival offset in camera px)."""
        k = self.atm_cfg.turbulence
        if k <= 0:
            return 1.0, np.zeros(2)
        rho = 0.3  # frame-to-frame correlation at 30 Hz (scintillation decorrelates in ~10 ms)
        sig_ln = 0.6 * k  # log-amplitude std
        self._scint = rho * self._scint + math.sqrt(1 - rho ** 2) * self.rt.standard_normal()
        factor = math.exp(sig_ln * self._scint - 0.5 * sig_ln ** 2)
        rho_a = 0.8
        self._aoa = rho_a * self._aoa + math.sqrt(1 - rho_a ** 2) * self.rt.standard_normal(2) * (1.5 * k)
        return factor, self._aoa.copy()

    # ---------------- image-plane disturbances --------------------------- #
    def apply_atmosphere_background(self, img: np.ndarray) -> np.ndarray:
        a = self.atm
        if a.airlight > 0:
            if self._veil is None or self._veil.shape != img.shape:
                h, w = img.shape
                yy = np.linspace(0.85, 1.15, h, dtype=np.float32)[:, None]
                self._veil = np.repeat(yy, w, axis=1)
            img = img * (0.3 + 0.7 * a.transmission) + a.airlight * self._veil
        return img

    def rain(self, img: np.ndarray) -> None:
        n = self.atm.rain_streaks
        if n <= 0:
            return
        h, w = img.shape
        r = self.rng
        xs = r.uniform(0, w, n)
        ys = r.uniform(0, h, n)
        L = r.uniform(8, 30, n)
        ang = math.radians(100) + r.normal(0, 0.08, n)
        lvl = r.uniform(25, 90, n)
        layer = np.zeros_like(img)
        for x, y, l, a_, v in zip(xs, ys, L, ang, lvl):
            x2, y2 = x + l * math.cos(a_), y + l * math.sin(a_)
            cv2.line(layer, (int(x), int(y)), (int(x2), int(y2)), float(v), 1, cv2.LINE_AA)
        img += layer

    def sensor(self, img: np.ndarray) -> np.ndarray:
        n = self.noise
        img = img * self.atm.gain
        if n.poisson:
            lam = np.clip(img, 0, None) * n.poisson_scale
            img = self.rng.poisson(lam).astype(np.float32) / n.poisson_scale
        if n.gaussian and n.gaussian_sigma > 0:
            img = img + self.rng.standard_normal(img.shape, dtype=np.float32) * n.gaussian_sigma
        out = np.clip(img, 0, 255).astype(np.uint8)
        if n.salt_pepper and n.salt_pepper_frac > 0:
            m = self.rng.random(out.shape, dtype=np.float32)
            f = n.salt_pepper_frac
            out[m < f / 2] = 0
            out[m > 1 - f / 2] = 255
        return out
