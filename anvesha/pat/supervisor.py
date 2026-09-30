"""PAT supervisor - detection -> association -> estimation -> search/control.

Mode machine (explicit, logged):
  SEARCH     no track; belief-driven (ANVESHA) or spiral (baselines) search
  ACQUIRE    tentative detection; needs M-of-N confirmation before locking
  TRACK      closed-loop tracking on measurements
  COAST      measurement lost; prediction-only tracking (bounded time)
  REACQUIRE  track lost; search seeded from the last prediction

Everything the supervisor uses is observable on a real terminal: camera
frames, gimbal encoders, IMU rates and the capture timestamps. Ground truth is
never passed in - it only reaches the metrics engine.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

from ..config import Config
from ..control.controllers import PIDController, PredictiveController
from ..estimation.filters import Estimator
from ..perception.detectors import Detection, Detector, FrameStats
from ..perception.learned import load_default
from ..search.belief import BeliefMap, BeliefPlanner, DetectionModel, PatternSearch

MODES = ["SEARCH", "ACQUIRE", "TRACK", "COAST", "REACQUIRE"]


@dataclass
class FrameReport:
    t: float
    mode: str
    detections: List[Detection]
    chosen: Optional[Detection]
    meas_g: Optional[np.ndarray]       # measurement in gimbal-frame (px)
    est_g: Optional[np.ndarray]        # estimate (gimbal frame, px)
    est_v: Optional[np.ndarray]
    est_sigma: float
    confidence: float
    stats: FrameStats
    proc_ms: float
    zoom: float
    plan_xy: Optional[np.ndarray] = None
    imm_mu: Optional[List[float]] = None
    nis: float = 0.0
    pd: float = 0.0
    events: List[str] = field(default_factory=list)


class Supervisor:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        c, g = cfg.camera, cfg.gimbal
        self.pipe = cfg.run.pipeline
        self.dpp = cfg.deg_per_px
        self.center_img = np.array([c.width_px / 2.0, c.height_px / 2.0])
        self.center = np.array([cfg.screen.width_px / 2.0, cfg.screen.height_px / 2.0])
        self.fov_half = np.array([c.width_px / 2.0, c.height_px / 2.0])
        self.max_rate = np.array([g.max_pan_rate_dps, g.max_tilt_rate_dps]) / self.dpp
        self.max_acc = g.max_accel_dps2 / self.dpp
        p = cfg.perception
        need_cnn = p.detector in ("cnn",) or (p.detector == "fusion" and p.use_cnn_verifier)
        self.cnn = load_default() if need_cnn else None
        self.detector = Detector(p.detector, p.cfar_k, p.centroid, self.cnn, p.use_cnn_verifier)
        e = cfg.estimator
        self.est = None if e.kind == "none" else Estimator(e.kind, e.q_cv, e.q_ct, e.q_ca, e.meas_sigma_px,
                                                            e.adaptive_r, e.gate_chi2)
        ctl = cfg.control
        total_lat = g.actuator_latency_s + g.rate_loop_tau_s + p.latency_s + 0.5 / c.rate_hz
        if ctl.kind == "predictive":
            self.ctrl = PredictiveController(ctl.kp, self.max_rate, self.max_acc, total_lat,
                                             ctl.feedforward, ctl.imu_feedforward and cfg.platform.imu_available,
                                             ctl.latency_comp)
        else:
            self.ctrl = PIDController(ctl.kp, ctl.ki, ctl.kd, self.max_rate, self.max_acc)
        s = cfg.search
        self.search_kind = s.kind
        self.bm = BeliefMap(cfg.screen.width_px, cfg.screen.height_px, s.cell_px, s.target_speed_prior_px_s)
        self.dm = DetectionModel(p.cfar_k, cfg.target.size_px, cfg.target.peak_level)
        zooms = c.zoom_levels if s.allow_zoom else [1.0]
        self.planner = BeliefPlanner(self.bm, self.dm, self.fov_half, zooms, self.max_rate, c.zoom_change_s,
                                     1.0 / c.rate_hz, s.dwell_frames, s.allow_zoom)
        self.pattern = PatternSearch("spiral" if s.kind != "raster" else "raster", self.center, self.fov_half,
                                     cfg.screen.width_px, cfg.screen.height_px)
        self.mode = "SEARCH"
        self.zoom_cmd = 1.0
        self.pending: Deque[Tuple[float, np.ndarray]] = deque(maxlen=4)
        self.last_meas_t = -1e9
        self.last_meas_g: Optional[np.ndarray] = None
        self.lost_at: Optional[float] = None
        self.coast_s = e.coast_s
        self.confidence = 0.0
        self.events: List[str] = []
        self.imu_last = np.zeros(2)
        self.plan_xy: Optional[np.ndarray] = None
        self.blacklist: List[np.ndarray] = []   # gimbal-frame positions of rejected static look-alikes
        self.static_for = 0.0
        self.plat_int = np.zeros(2)            # integrated IMU rate = platform LOS offset estimate (px)
        self.smap_t = np.zeros(0); self.smap_w = np.zeros((0, 2))   # recent detections in the world frame
        self.jit_seen = 0.0
        self.world_hist: Deque[Tuple[float, np.ndarray]] = deque(maxlen=64)
        self.frame_dt = 1.0 / c.rate_hz
        self.last_t = 0.0
        self.a_err = np.zeros(2)   # baseline A: last measured error
        self.confirm_n = 1 if self.pipe == "baseline_a" else (3 if self.pipe == "anvesha" else 2)

    # ------------------------------------------------------------------ #
    def _event(self, t: float, msg: str) -> None:
        self.events.append(f"{t:7.2f}s  {msg}")

    def _set_mode(self, t: float, m: str, why: str = "") -> None:
        if m != self.mode:
            self._event(t, f"{self.mode} -> {m}" + (f" ({why})" if why else ""))
            self.mode = m

    def to_g(self, uv: np.ndarray, gimbal_enc: np.ndarray, zoom: float) -> np.ndarray:
        """Camera pixel -> gimbal-frame coordinates (screen px, centred frame)."""
        return self.center + gimbal_enc + zoom * (uv - self.center_img)

    def to_uv(self, g: np.ndarray, gimbal_enc: np.ndarray, zoom: float) -> np.ndarray:
        return (g - self.center - gimbal_enc) / zoom + self.center_img

    # ------------------------------------------------------------------ #
    def on_frame(self, t: float, frame: np.ndarray, gimbal_enc: np.ndarray, zoom: float, zoom_settling: bool,
                 imu_rate: np.ndarray) -> FrameReport:
        t0 = time.perf_counter()
        self.events = []
        dt = max(t - self.last_t, 1e-3)
        self.last_t = t
        self.imu_last = imu_rate
        if self.cfg.platform.imu_available:
            self.plat_int = self.plat_int + imu_rate * dt
        if self.blacklist and self.cfg.platform.imu_available:
            # static world objects drift in the gimbal frame opposite to platform rotation
            self.blacklist = [p_ - imu_rate * dt for p_ in self.blacklist]
        exp_size = self.cfg.target.size_px / zoom
        # ---- ROI from prediction ------------------------------------- #
        roi = None
        pred_g = None
        if self.est is not None and self.est.initialised and self.mode in ("TRACK", "COAST", "ACQUIRE"):
            u_in = -imu_rate if self.cfg.control.imu_feedforward and self.cfg.platform.imu_available else np.zeros(2)
            self.est.predict_to(t, u_in)
            pred_g = self.est.x[:2]
            puv = self.to_uv(pred_g, gimbal_enc, zoom)
            sig = self.est.pos_sigma() / zoom
            half = min(max(self.cfg.perception.roi_scale * exp_size, 4 * sig + 2 * exp_size, 40), 260)
            roi = (puv[0], puv[1], half)
        elif self.pipe == "baseline_a" and self.mode == "TRACK" and self.last_meas_g is not None:
            puv = self.to_uv(self.last_meas_g, gimbal_enc, zoom)
            roi = (puv[0], puv[1], 80)
        if zoom_settling:
            dets, st = [], FrameStats()
        else:
            dets, st = self.detector.detect(frame, exp_size, roi)
            if not dets and roi is not None and self.mode in ("TRACK", "COAST"):
                # widen to full frame once before giving up on this frame
                dets, st = self.detector.detect(frame, exp_size, None)
        self.dm.observe_noise(st.pix_sigma, st.sp_frac)
        if dets and self.pipe == "anvesha" and self.cfg.search.reject_static and self.mode in ("SEARCH", "REACQUIRE"):
            self._static_map(t, dets, gimbal_enc, zoom)
        # ---- association --------------------------------------------- #
        chosen, z = None, None
        min_score = 0.35 if self.pipe == "anvesha" else 0.0
        if dets:
            if self.est is not None and self.est.initialised and self.mode in ("TRACK", "COAST", "ACQUIRE"):
                best, bs = None, -1.0
                for d in dets:
                    zg = self.to_g(np.array([d.u, d.v]), gimbal_enc, zoom)
                    d2, lik = self.est.gate_and_score(zg)
                    gate = self.est.gate * (4.0 if self.mode == "COAST" else 1.0)
                    if d2 <= gate and d.score >= min_score:
                        s = d.score * math.exp(-0.5 * d2 / 4.0)
                        if s > bs:
                            best, bs = d, s
                chosen = best
                if chosen is None and self.mode in ("TRACK", "COAST") and self.pipe == "anvesha":
                    # manoeuvre re-anchor: no candidate inside the statistical gate, but a
                    # strong, verified, beacon-shaped candidate close to the prediction ->
                    # accept it and re-initialise the velocity (abrupt direction change).
                    radius = 3 * exp_size * zoom + 400.0 * max(t - self.last_meas_t, self.frame_dt) + 20
                    strong = [d for d in dets if d.score >= 0.6 and (d.cnn < 0 or d.cnn >= 0.5)]
                    for d in strong:
                        zg = self.to_g(np.array([d.u, d.v]), gimbal_enc, zoom)
                        if np.linalg.norm(zg - self.est.x[:2]) <= radius:
                            self.est.init(zg, t, None, 3.0, 300.0)
                            self._event(t, "manoeuvre re-anchor")
                            chosen = d
                            break
            else:
                cand = [d for d in dets if d.score >= min_score]
                if self.blacklist:
                    cand = [d for d in cand if min(np.linalg.norm(self.to_g(np.array([d.u, d.v]), gimbal_enc, zoom) - b_) for b_ in self.blacklist) > 3 * self.cfg.target.size_px + 10]
                if self.pipe == "anvesha":
                    # among plausible candidates prefer the strongest beacon-like return
                    cand.sort(key=lambda d: -(d.score * min(1.0, d.snr / 40.0)))
                if self.pipe == "baseline_a" and self.mode == "TRACK" and self.last_meas_g is not None:
                    cand.sort(key=lambda d: np.linalg.norm(self.to_g(np.array([d.u, d.v]), gimbal_enc, zoom) - self.last_meas_g))
                chosen = cand[0] if cand else None
            if chosen is not None:
                z = self.to_g(np.array([chosen.u, chosen.v]), gimbal_enc, zoom)
                self.dm.observe_beacon(chosen.peak)
        # ---- mode logic ---------------------------------------------- #
        nis = 0.0
        if self.mode in ("SEARCH", "REACQUIRE"):
            if z is not None:
                self.pending.clear()
                self.pending.append((t, z))
                if self.confirm_n <= 1:
                    self._lock(t, z, None)
                else:
                    self._set_mode(t, "ACQUIRE", f"candidate SNR {chosen.snr:.1f}")
            else:
                self._search_update(t, dt, gimbal_enc, zoom, zoom_settling)
        elif self.mode == "ACQUIRE":
            if z is not None and (np.linalg.norm(z - self.pending[-1][1]) < 3 * exp_size * zoom + 60 * (t - self.pending[-1][0]) + 30):
                self.pending.append((t, z))
                if len(self.pending) >= self.confirm_n:
                    (t1, z1), (t2, z2) = self.pending[-2], self.pending[-1]
                    v = (z2 - z1) / max(t2 - t1, 1e-3)
                    self._lock(t, z2, v)
            else:
                if t - self.pending[-1][0] > 3 * self.frame_dt:
                    self._set_mode(t, "REACQUIRE" if self.lost_at is not None else "SEARCH", "confirmation failed")
                    self.pending.clear()
        elif self.mode in ("TRACK", "COAST"):
            if z is not None:
                if self.est is not None:
                    nis = self.est.update(z)
                self.last_meas_t = t
                self.last_meas_g = z
                if self.mode == "COAST":
                    self._set_mode(t, "TRACK", "measurement regained")
                if zoom > 1.0 and self.search_kind == "belief":
                    # zoom back in for precision once the beacon is near the boresight
                    if np.max(np.abs(z - (self.center + gimbal_enc))) < 0.25 * self.fov_half[0]:
                        self.zoom_cmd = 1.0
            else:
                if self.mode == "TRACK" and not zoom_settling:
                    self._set_mode(t, "COAST", "no measurement")
                coast_for = t - self.last_meas_t
                too_uncertain = self.est is not None and self.est.pos_sigma() > 0.8 * self.fov_half[1] * zoom
                if coast_for > self.coast_s or too_uncertain:
                    self._lose(t, gimbal_enc)
        # ---- confidence ---------------------------------------------- #
        # static look-alike rejection (designated target is a moving beacon)
        sc_ = self.cfg.search
        if (sc_.reject_static and self.pipe == "anvesha" and self.mode == "TRACK" and self.est is not None
                and self.est.initialised and chosen is not None):
            # world-frame displacement test: tracked position + integrated platform motion (IMU).
            # A static look-alike stays put in the world even when the platform moves it across the image.
            wpos = self.est.x[:2] + self.plat_int
            self.world_hist.append((t, wpos.copy()))
            while self.world_hist and t - self.world_hist[0][0] > sc_.static_s:
                self.world_hist.popleft()
            span = t - self.world_hist[0][0] if self.world_hist else 0.0
            W = np.array([w_ for _, w_ in self.world_hist])
            extent = float(np.max(np.ptp(W, axis=0))) if len(W) > 1 else 1e9   # a reversing target still spans its path
            self.jit_seen = max(self.jit_seen, float(getattr(self.est, "jitter_sigma", 0.0)))
            if span >= 0.9 * sc_.static_s and extent < sc_.static_disp_px + 0.8 * self.jit_seen:
                self.static_for = sc_.static_s + 1e-6
            elif np.linalg.norm(self.est.x[2:4]) < sc_.static_speed_px_s:
                self.static_for += dt
            else:
                self.static_for = 0.0
            if self.static_for > sc_.static_s:
                self.blacklist.append(self.est.x[:2].copy())
                self._event(t, "static look-alike rejected - resuming search")
                self.static_for = 0.0
                self.world_hist.clear()
                self.est.initialised = False
                # keep the pre-lock belief (the misses before the false lock are still valid evidence);
                # only diffuse it for the time spent on the look-alike
                self.bm.predict(max(t - self.last_meas_t, 0.0) + sc_.static_s)
                self.planner.plan = None
                self._set_mode(t, "SEARCH", "look-alike")
                chosen = None
        if self.mode == "TRACK" and chosen is not None:
            cons = self.est.consistency() if self.est is not None else 0.7
            self.confidence = 0.7 * self.confidence + 0.3 * (0.6 * chosen.score + 0.4 * cons)
        elif self.mode == "COAST":
            self.confidence *= 0.85
        elif self.mode in ("SEARCH", "REACQUIRE"):
            self.confidence = 0.0
        proc = (time.perf_counter() - t0) * 1000.0
        est_g = self.est.x[:2].copy() if (self.est is not None and self.est.initialised) else (self.last_meas_g if self.pipe == "baseline_a" else None)
        est_v = self.est.x[2:4].copy() if (self.est is not None and self.est.initialised) else None
        return FrameReport(t, self.mode, dets, chosen, z, est_g, est_v,
                           self.est.pos_sigma() if (self.est is not None and self.est.initialised) else 0.0,
                           self.confidence, st, proc, zoom, self.plan_xy,
                           self.est.mu.tolist() if (self.est is not None and self.est.initialised) else None,
                           nis, self.planner.expected_pd(zoom) if self.mode in ("SEARCH", "REACQUIRE") else self.dm.pd(zoom), list(self.events))

    def _static_map(self, t: float, dets, gimbal_enc: np.ndarray, zoom: float) -> None:
        """Pre-lock look-alike rejection: a detection that re-appears at the same *world* position
        (gimbal frame + integrated IMU platform motion) after >= static_revisit_s is a static object,
        not the moving beacon -> blacklist it without spending a lock on it."""
        sc_ = self.cfg.search
        if self.est is not None:
            self.jit_seen = max(self.jit_seen, float(getattr(self.est, "jitter_sigma", 0.0)))
        thr = sc_.static_disp_px + 2.5 * self.jit_seen
        keep = self.smap_t > t - 4.0
        self.smap_t, self.smap_w = self.smap_t[keep], self.smap_w[keep]
        tracked = self.est.x[:2] if (self.est is not None and self.est.initialised) else None
        new_w = []
        for d in [d_ for d_ in dets[:12] if d_.score >= 0.5 and (d_.cnn < 0 or d_.cnn >= 0.5)]:
            g = self.to_g(np.array([d.u, d.v]), gimbal_enc, zoom)
            w = g + self.plat_int
            new_w.append(w)
            old = self.smap_t <= t - sc_.static_revisit_s
            if not old.any():
                continue
            dist = np.linalg.norm(self.smap_w[old] - w, axis=1)
            if (dist < thr).sum() >= 2:
                if any(np.linalg.norm(g - b_) < thr for b_ in self.blacklist):
                    continue
                self.blacklist.append(g.copy())
                self._event(t, "static object mapped - excluded from acquisition")
        if new_w:
            self.smap_t = np.concatenate([self.smap_t, np.full(len(new_w), t)])
            self.smap_w = np.vstack([self.smap_w, np.array(new_w)])
            if len(self.smap_t) > 3000:
                self.smap_t, self.smap_w = self.smap_t[-3000:], self.smap_w[-3000:]

    # ------------------------------------------------------------------ #
    def _lock(self, t: float, z: np.ndarray, v: Optional[np.ndarray]) -> None:
        if self.est is not None:
            self.est.init(z, t, v if v is not None else np.zeros(2), 4.0, 120.0 if v is not None else 250.0)
        self.last_meas_t = t
        self.last_meas_g = z
        self.pending.clear()
        self.planner.plan = None
        self.plan_xy = None
        if hasattr(self.ctrl, "reset"):
            self.ctrl.reset()
        self.world_hist.clear()
        self.static_for = 0.0
        why = "re-acquired" if self.lost_at is not None else "acquired"
        self._set_mode(t, "TRACK", why)
        self.lost_at = None

    def _lose(self, t: float, gimbal_enc: np.ndarray) -> None:
        self.lost_at = t
        self._set_mode(t, "REACQUIRE", "track lost")
        self.pending.clear()
        if self.search_kind == "belief":
            if self.est is not None and self.est.initialised:
                self.bm.reset_gaussian(self.est.x[:2], self.est.P[:2, :2] + np.eye(2) * 400.0, self.est.x[2:4],
                                       weights=self.dm.weights_from_measured())
            else:
                self.bm.reset_uniform()
            self.planner.plan = None
        else:
            last = self.last_meas_g if self.last_meas_g is not None else self.center + gimbal_enc
            if self.est is not None and self.est.initialised:
                last = self.est.x[:2]
            self.pattern = PatternSearch(self.pattern.kind, last, self.fov_half, self.cfg.screen.width_px,
                                         self.cfg.screen.height_px)
        if self.est is not None:
            self.est.initialised = False

    def _search_update(self, t: float, dt: float, gimbal_enc: np.ndarray, zoom: float, settling: bool) -> None:
        bore = self.center + gimbal_enc
        if self.search_kind == "belief":
            self.bm.predict(dt)
            if abs(self.imu_last).sum() > 0 and self.cfg.platform.imu_available:
                # platform rotation moves the target in the gimbal frame
                M = -self.imu_last * dt / self.bm.cell
                if np.max(np.abs(M)) > 1e-3:
                    import cv2
                    A = np.float32([[1, 0, M[0]], [0, 1, M[1]]])
                    for k in range(self.bm.K):
                        self.bm.B[k] = cv2.warpAffine(self.bm.B[k].astype(np.float32), A, (self.bm.nx, self.bm.ny),
                                                      borderMode=cv2.BORDER_REPLICATE)
                    self.bm._norm()
            if not settling:
                self.bm.miss_update(bore, self.fov_half * zoom, self.dm.pd_vec(zoom))
            plan = self.planner.choose(bore, zoom)
            self.plan_xy = plan.xy
            self.zoom_cmd = plan.zoom
        else:
            self.plan_xy = self.pattern.target(bore)

    # ------------------------------------------------------------------ #
    def control(self, t: float, gimbal_enc: np.ndarray, gimbal_rate: np.ndarray, imu_rate: np.ndarray) -> np.ndarray:
        """Called at the control rate (>= 20 Hz). Returns gimbal rate command (px/s)."""
        bore = self.center + gimbal_enc
        if self.mode in ("TRACK", "COAST") or (self.mode == "ACQUIRE" and self.est is not None and self.est.initialised):
            if isinstance(self.ctrl, PredictiveController) and self.est is not None and self.est.initialised:
                u_in = -imu_rate if (self.cfg.control.imu_feedforward and self.cfg.platform.imu_available) else np.zeros(2)
                dt = t - self.est.t
                x = self.est.x
                pos = x[:2] + (x[2:4] + u_in) * dt
                return self.ctrl.track(pos - self.center, x[2:4], gimbal_enc, gimbal_rate,
                                       imu_rate if self.cfg.platform.imu_available else None)
            # PID baselines: error = (estimate or last measurement) - boresight
            if self.est is not None and self.est.initialised:
                err = self.est.x[:2] - bore
            elif self.last_meas_g is not None:
                err = self.last_meas_g - bore
            else:
                err = np.zeros(2)
            if self.mode == "COAST" and self.est is None:
                return np.zeros(2)
            return self.ctrl.track(err, 1.0 / self.cfg.control.rate_hz)
        if self.mode == "ACQUIRE" and self.pending:
            err = self.pending[-1][1] - bore
            return self.ctrl.slew(err) if isinstance(self.ctrl, PIDController) else self.ctrl.slew(err, imu_rate)
        if self.plan_xy is not None:
            err = self.plan_xy - bore
            return self.ctrl.slew(err) if isinstance(self.ctrl, PIDController) else self.ctrl.slew(err, imu_rate)
        return np.zeros(2)
