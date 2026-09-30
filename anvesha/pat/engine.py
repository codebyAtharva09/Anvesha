"""Multi-rate closed-loop engine: SimWorld <-> Supervisor, with telemetry.

Rates (defaults): simulation 240 Hz, camera 30 Hz, control 60 Hz, UI 15-30 Hz.
The same engine drives the headless benchmark runner and the live GUI, so the
numbers shown on screen are the numbers written to the logs.
"""
from __future__ import annotations

import math
import time
from collections import deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

import numpy as np

from ..config import Config
from ..metrics.metrics import MetricsEngine
from ..sim.world import SimWorld, Truth
from .supervisor import FrameReport, Supervisor


class Engine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.world = SimWorld(cfg)
        self.sup = Supervisor(cfg)
        self.metrics = MetricsEngine(cfg)
        self.sim_dt = 1.0 / cfg.run.sim_rate_hz
        self.cam_every = max(int(round(cfg.run.sim_rate_hz / cfg.camera.rate_hz)), 1)
        self.ctl_every = max(int(round(cfg.run.sim_rate_hz / cfg.control.rate_hz)), 1)
        self.k = 0
        self.lat_steps = int(round(cfg.perception.latency_s / self.sim_dt))
        self.pending: Deque[Tuple[int, float, np.ndarray, Truth, np.ndarray, float, bool, np.ndarray]] = deque()
        self.last_frame: Optional[np.ndarray] = None
        self.last_truth: Optional[Truth] = None
        self.last_report: Optional[FrameReport] = None
        self.last_cmd = np.zeros(2)
        self.event_log: List[str] = []
        self.loop_ms: Deque[float] = deque(maxlen=120)
        self._t_wall = time.perf_counter()

    @property
    def t(self) -> float:
        return self.world.t

    def step(self) -> Optional[FrameReport]:
        """Advance one simulation tick; returns a FrameReport when a frame was processed."""
        w, s = self.world, self.sup
        rep = None
        if self.k % self.cam_every == 0:
            t0 = time.perf_counter()
            frame, truth = w.capture()
            enc = w.gimbal.angle.copy()
            self.pending.append((self.k + self.lat_steps, w.t, frame, truth, enc, w.zoom,
                                 truth.zoom_settling, w.imu_rate()))
            self.last_frame, self.last_truth = frame, truth
            self._render_ms = (time.perf_counter() - t0) * 1000
        while self.pending and self.pending[0][0] <= self.k:
            _, tc, frame, truth, enc, zoom, settling, imu = self.pending.popleft()
            t0 = time.perf_counter()
            rep = s.on_frame(tc, frame, enc, zoom, settling, imu)
            if abs(s.zoom_cmd - w.zoom) > 1e-6:
                w.set_zoom(s.zoom_cmd)
            self.metrics.add(truth, rep, getattr(self, "_render_ms", 0.0))
            for e in rep.events:
                self.event_log.append(e)
            self.last_report = rep
            now = time.perf_counter()
            self.loop_ms.append((now - self._t_wall) * 1000)
            self._t_wall = now
        if self.k % self.ctl_every == 0:
            cmd = s.control(w.t, w.gimbal.angle.copy(), w.gimbal.rate.copy(), w.imu_rate())
            w.command_rate(cmd)
            self.last_cmd = cmd
        w.step(self.sim_dt)
        self.k += 1
        return rep

    def run(self, duration: Optional[float] = None, on_frame: Optional[Callable] = None) -> Dict:
        T = duration if duration is not None else self.cfg.run.duration_s
        n = int(round(T / self.sim_dt))
        for _ in range(n):
            rep = self.step()
            if rep is not None and on_frame is not None:
                on_frame(self, rep)
        return self.metrics.summary()
