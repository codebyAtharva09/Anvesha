"""SimWorld - the software-in-the-loop plant.

Owns the virtual screen, beacon trajectory, mobile platform + IMU, rate-
commanded gimbal, zoom and the disturbance engine. It is advanced at the
simulation rate (default 240 Hz) and produces camera frames at the camera
rate (default 30 Hz) together with *ground truth* that is never visible to
the tracking pipeline (it only feeds the metrics engine).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from ..config import Config
from . import trajectories as trj
from .disturbances import Disturbances
from .optics import Scene, render_spot
from .platform import IMU, Gimbal, PlatformMotion


@dataclass
class Truth:
    t: float
    target_xy: np.ndarray            # screen px
    target_vel: np.ndarray           # screen px/s
    boresight_xy: np.ndarray         # true LOS incl. platform + jitter (screen px)
    los_nojitter_xy: np.ndarray      # LOS from gimbal + platform only
    gimbal_px: np.ndarray            # gimbal angles (screen px)
    gimbal_rate_px: np.ndarray
    platform_px: np.ndarray
    platform_rate_px: np.ndarray
    jitter_px: np.ndarray
    beacon_uv: np.ndarray            # true beacon centre in the camera image (px)
    visible: bool                    # beacon inside FOV and not occluded
    occluded: bool
    zoom: float
    zoom_settling: bool
    in_fov: bool
    extra: Dict = field(default_factory=dict)


class SimWorld:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        ss = np.random.SeedSequence(cfg.run.seed)
        kids = ss.spawn(8)
        self.rng_traj, self.rng_plat, self.rng_img, self.rng_turb, self.rng_jit, self.rng_scene, self.rng_imu, self.rng_misc = [
            np.random.Generator(np.random.PCG64(k)) for k in kids]
        c, s, t, g, p = cfg.camera, cfg.screen, cfg.target, cfg.gimbal, cfg.platform
        self.dpp = cfg.deg_per_px
        self.W, self.H = s.width_px, s.height_px
        self.center = np.array([self.W / 2.0, self.H / 2.0])
        self.scene = Scene(self.W, self.H, s.background, s.background_level, s.n_stars, s.n_distractors,
                           s.distractor_level, t.size_px, self.rng_scene)
        start = None
        if t.initial == "center":
            start = tuple(self.center)
        elif t.initial == "xy" and t.initial_xy:
            start = tuple(t.initial_xy)
        self.targets: List[trj.Trajectory] = [
            trj.make(t.trajectory, self.W, self.H, t.speed_px_s, self.rng_traj, start, t.radius_px, t.user_waypoints)]
        for _ in range(max(t.n_targets, 1) - 1):
            self.targets.append(trj.make("random", self.W, self.H, t.speed_px_s * 0.8, self.rng_traj))
        self.platform = PlatformMotion(p.motion, p.amplitude_px_per_frame, c.rate_hz, p.period_s,
                                       p.vibration_hz, self.rng_plat)
        self.imu = IMU(p.imu_noise_dps / self.dpp, p.imu_bias_dps / self.dpp, self.rng_imu)
        self.sim_dt = 1.0 / cfg.run.sim_rate_hz
        self.gimbal = Gimbal((g.max_pan_rate_dps / self.dpp, g.max_tilt_rate_dps / self.dpp),
                             g.max_accel_dps2 / self.dpp, g.rate_loop_tau_s, g.actuator_latency_s,
                             (g.pan_limit_deg / self.dpp, g.tilt_limit_deg / self.dpp), self.sim_dt)
        if not g.start_centered:
            self.gimbal.angle = self.rng_misc.uniform(-300, 300, 2)
        self.dist = Disturbances(cfg.noise, cfg.atmosphere, self.rng_img, self.rng_turb, self.rng_jit)
        self.t = 0.0
        self.zoom = 1.0
        self._zoom_busy_until = -1.0
        self.frame_idx = 0
        self.manual_occlusion = False

    # ------------------------------------------------------------------ #
    def set_zoom(self, z: float) -> None:
        if abs(z - self.zoom) > 1e-6:
            self.zoom = float(z)
            self._zoom_busy_until = self.t + self.cfg.camera.zoom_change_s

    def command_rate(self, rate_px_s: np.ndarray) -> None:
        self.gimbal.command(rate_px_s)

    def step(self, dt: Optional[float] = None) -> None:
        dt = dt or self.sim_dt
        for tg in self.targets:
            tg.step(dt)
        self.platform.step(dt)
        self.gimbal.step(dt)
        self.t += dt

    def imu_rate(self) -> np.ndarray:
        """IMU-measured platform LOS rate (px/s) - available to the controller."""
        return self.imu.read(self.platform.rate)

    def occluded(self) -> bool:
        if self.manual_occlusion:
            return True
        for a, b in self.cfg.target.occlusions:
            if a <= self.t < b:
                return True
        return False

    # ------------------------------------------------------------------ #
    def capture(self):
        """Render one camera frame. Returns (uint8 image, Truth)."""
        c, tcfg = self.cfg.camera, self.cfg.target
        w, h = c.width_px, c.height_px
        z = self.zoom
        jit = self.dist.jitter()
        los0 = self.center + self.gimbal.angle + self.platform.offset
        bore = los0 + jit
        img = self.scene.crop(bore[0], bore[1], z, w, h)
        img = self.dist.apply_atmosphere_background(img)
        occ = self.occluded()
        scint, aoa = self.dist.turbulence()
        atm = self.dist.atm
        tgt = self.targets[0]
        uv = (tgt.pos - bore) / z + np.array([w / 2.0, h / 2.0]) + aoa
        size_cam = tcfg.size_px / z
        psf = math.sqrt(c.psf_sigma_px ** 2 + atm.blur_sigma ** 2)
        peak = tcfg.peak_level * atm.transmission * scint
        if tcfg.blink_hz > 0 and math.sin(2 * math.pi * tcfg.blink_hz * self.t) < -0.2:
            peak *= 0.35
        # (forward-scatter blur is applied by convolution inside render_spot, which conserves flux)
        if not occ:
            render_spot(img, uv[0], uv[1], size_cam, peak, psf, tcfg.shape)
        for other in self.targets[1:]:
            uvo = (other.pos - bore) / z + np.array([w / 2.0, h / 2.0])
            render_spot(img, uvo[0], uvo[1], size_cam, peak, psf, tcfg.shape)
        self.dist.rain(img)
        frame = self.dist.sensor(img)
        in_fov = (0 <= uv[0] < w) and (0 <= uv[1] < h)
        settling = self.t < self._zoom_busy_until
        truth = Truth(
            t=self.t, target_xy=tgt.pos.copy(), target_vel=tgt.vel.copy(), boresight_xy=bore.copy(),
            los_nojitter_xy=los0.copy(), gimbal_px=self.gimbal.angle.copy(), gimbal_rate_px=self.gimbal.rate.copy(),
            platform_px=self.platform.offset.copy(), platform_rate_px=self.platform.rate.copy(), jitter_px=jit,
            beacon_uv=uv, visible=bool(in_fov and not occ), occluded=occ, zoom=z, zoom_settling=settling,
            in_fov=bool(in_fov), extra={"scint": scint, "saturated": self.gimbal.saturated.tolist()})
        self.frame_idx += 1
        return frame, truth
