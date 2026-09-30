"""Target (beacon) trajectory generators on the virtual screen.

All trajectories are expressed in *screen pixels* (x to the right, y down,
origin at the top-left corner) and are advanced with a fixed simulation step,
so they are bit-reproducible for a given seed.

PS26169 #12: straight line, circular, figure-of-8 and random are mandatory;
spiral, sinusoidal and user-defined are optional - all seven are provided.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np


class Trajectory:
    """Base class. `step(dt)` advances time; `pos`/`vel` are screen px, px/s."""

    def __init__(self, W: int, H: int, speed: float, rng: np.random.Generator,
                 start: Optional[Tuple[float, float]] = None, margin: float = 60.0):
        self.W, self.H, self.speed, self.rng, self.margin = W, H, speed, rng, margin
        if start is None:
            start = (rng.uniform(margin + 200, W - margin - 200), rng.uniform(margin + 200, H - margin - 200))
        self.p0 = np.array(start, dtype=float)
        self.pos = self.p0.copy()
        self.vel = np.zeros(2)
        self.t = 0.0

    def _bounce(self):
        m = self.margin
        for i, lim in ((0, self.W), (1, self.H)):
            if self.pos[i] < m:
                self.pos[i] = 2 * m - self.pos[i]
                self.vel[i] = abs(self.vel[i])
            elif self.pos[i] > lim - m:
                self.pos[i] = 2 * (lim - m) - self.pos[i]
                self.vel[i] = -abs(self.vel[i])

    def step(self, dt: float) -> None:  # pragma: no cover - abstract
        raise NotImplementedError


class Static(Trajectory):
    def step(self, dt):
        self.t += dt


class Straight(Trajectory):
    """Constant-velocity straight line; reflects at the screen margin."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        ang = self.rng.uniform(0, 2 * math.pi)
        self.vel = self.speed * np.array([math.cos(ang), math.sin(ang)])

    def step(self, dt):
        self.t += dt
        self.pos = self.pos + self.vel * dt
        self._bounce()


class _Parametric(Trajectory):
    """Trajectory defined by a closed-form function f(t) around a centre."""

    def __init__(self, *a, radius: float = 300.0, **k):
        super().__init__(*a, **k)
        R = radius
        # keep the whole curve inside the screen
        lo, hi = self.margin + R + 10, None
        cx = float(np.clip(self.p0[0], self.margin + R + 10, self.W - self.margin - R - 10))
        cy = float(np.clip(self.p0[1], self.margin + R + 10, self.H - self.margin - R - 10))
        self.c = np.array([cx, cy])
        self.R = R
        self.phase = self.rng.uniform(0, 2 * math.pi)
        self.pos = self.f(0.0)
        self.vel = (self.f(1e-3) - self.f(0.0)) / 1e-3

    def f(self, t: float) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def step(self, dt):
        self.t += dt
        p = self.f(self.t)
        self.vel = (p - self.pos) / dt
        self.pos = p


class Circular(_Parametric):
    def f(self, t):
        w = self.speed / self.R
        a = self.phase + w * t
        return self.c + self.R * np.array([math.cos(a), math.sin(a)])


class Figure8(_Parametric):
    """Lissajous 1:2 figure-of-eight (Gerono-like), mean speed ~= `speed`."""

    def f(self, t):
        # path length of (R sin a, R/2 sin 2a) over one period ~= 6.1 R
        w = 2 * math.pi * self.speed / (6.1 * self.R)
        a = self.phase + w * t
        return self.c + np.array([self.R * math.sin(a), 0.5 * self.R * math.sin(2 * a)])


class Spiral(_Parametric):
    """Archimedean spiral that breathes in and out between 0.2R and R."""

    def f(self, t):
        r = self.R * (0.6 + 0.4 * math.sin(2 * math.pi * t / 30.0))
        w = self.speed / max(r, 1.0)
        # integrate angle approximately with the mean radius for smoothness
        a = self.phase + self.speed * t / (0.6 * self.R)
        return self.c + r * np.array([math.cos(a), math.sin(a)])


class Sinusoidal(Trajectory):
    """Moves along a random heading with a sinusoidal cross-track component."""

    def __init__(self, *a, amplitude: float = 200.0, period: float = 6.0, **k):
        super().__init__(*a, **k)
        ang = self.rng.uniform(0, 2 * math.pi)
        self.u = np.array([math.cos(ang), math.sin(ang)])
        self.n = np.array([-self.u[1], self.u[0]])
        self.A, self.P = amplitude, period
        self.s = 0.0
        self.base = self.p0.copy()

    def step(self, dt):
        self.t += dt
        self.s += self.speed * dt
        p = self.base + self.u * self.s + self.n * self.A * math.sin(2 * math.pi * self.t / self.P)
        # reflect heading at the borders
        m = self.margin + self.A
        if not (m < p[0] < self.W - m and m < p[1] < self.H - m):
            self.base = self.pos - self.n * self.A * math.sin(2 * math.pi * self.t / self.P)
            self.s = 0.0
            self.u = -self.u
            p = self.base + self.n * self.A * math.sin(2 * math.pi * self.t / self.P)
        self.vel = (p - self.pos) / dt
        self.pos = p


class RandomWalk(Trajectory):
    """Ornstein-Uhlenbeck velocity process: smooth but unpredictable manoeuvres,
    including abrupt heading changes; speed is softly bounded to ~1.6x `speed`."""

    def __init__(self, *a, tau: float = 1.5, **k):
        super().__init__(*a, **k)
        self.tau = tau
        ang = self.rng.uniform(0, 2 * math.pi)
        self.vel = self.speed * np.array([math.cos(ang), math.sin(ang)])

    def step(self, dt):
        self.t += dt
        sig = self.speed * math.sqrt(2.0 / self.tau)
        self.vel = self.vel + (-self.vel / self.tau) * dt + sig * math.sqrt(dt) * self.rng.standard_normal(2)
        # keep a minimum and maximum speed so the target keeps moving
        sp = float(np.linalg.norm(self.vel))
        if sp > 1.6 * self.speed:
            self.vel *= 1.6 * self.speed / sp
        elif sp < 0.3 * self.speed:
            self.vel *= 0.3 * self.speed / max(sp, 1e-6)
        self.pos = self.pos + self.vel * dt
        self._bounce()


class UserDefined(Trajectory):
    """Piece-wise linear path through user waypoints at constant speed (loops)."""

    def __init__(self, *a, waypoints: Optional[List[List[float]]] = None, **k):
        super().__init__(*a, **k)
        if not waypoints:
            c = np.array([self.W / 2, self.H / 2])
            waypoints = [list(c + d) for d in ([-400, -300], [400, -300], [400, 300], [-400, 300])]
        self.wp = [np.array(w, dtype=float) for w in waypoints]
        self.pos = self.wp[0].copy()
        self.i = 1

    def step(self, dt):
        self.t += dt
        remaining = self.speed * dt
        while remaining > 1e-9:
            tgt = self.wp[self.i % len(self.wp)]
            d = tgt - self.pos
            L = float(np.linalg.norm(d))
            if L <= remaining:
                self.pos = tgt.copy()
                remaining -= L
                self.i += 1
            else:
                self.pos = self.pos + d / L * remaining
                self.vel = d / L * self.speed
                remaining = 0.0


def make(kind: str, W: int, H: int, speed: float, rng: np.random.Generator,
         start=None, radius: float = 300.0, waypoints=None) -> Trajectory:
    kind = kind.lower()
    if kind == "straight":
        return Straight(W, H, speed, rng, start)
    if kind == "circular":
        return Circular(W, H, speed, rng, start, radius=radius)
    if kind in ("figure8", "figure_of_8", "figure-8"):
        return Figure8(W, H, speed, rng, start, radius=radius)
    if kind == "spiral":
        return Spiral(W, H, speed, rng, start, radius=radius)
    if kind == "sinusoidal":
        return Sinusoidal(W, H, speed, rng, start)
    if kind == "random":
        return RandomWalk(W, H, speed, rng, start)
    if kind == "user":
        return UserDefined(W, H, speed, rng, start, waypoints=waypoints)
    if kind == "static":
        return Static(W, H, speed, rng, start)
    raise ValueError(f"unknown trajectory '{kind}'")
