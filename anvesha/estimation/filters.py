"""State estimation for the beacon line of sight.

The target is tracked in the *gimbal frame*: x_g = angle the gimbal must hold
to centre the beacon (screen px units; 1 px = deg_per_px deg).  A measurement
is  z = gimbal_encoder(t_capture) + zoom * (centroid - image_centre).
Platform rotation enters as a *known input* when an IMU is available:
    x_g(k+1) = x_g(k) + (v_target - w_platform_imu) * dt
so the filter's velocity states describe the (smooth) target motion and are
not corrupted by platform manoeuvres or vibration.

Estimators:
  KFCV  - constant-velocity Kalman filter (Baselines B/C)
  IMM   - Interacting Multiple Model (CV / CA / high-manoeuvre CV) with
          adaptive measurement noise (innovation covariance matching) so the
          loop does not chase frame-to-frame camera jitter.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

CHI2_2DOF_999 = 13.82


def _F(dt: float, model: str) -> np.ndarray:
    I2 = np.eye(2)
    Z = np.zeros((2, 2))
    if model == "ca":
        return np.block([[I2, dt * I2, 0.5 * dt * dt * I2], [Z, I2, dt * I2], [Z, Z, I2]])
    # constant velocity: acceleration states are reset (kept in the vector for IMM mixing)
    return np.block([[I2, dt * I2, Z], [Z, I2, Z], [Z, Z, Z]])


def _Q(dt: float, model: str, q: float) -> np.ndarray:
    I2 = np.eye(2)
    Z = np.zeros((2, 2))
    if model == "ca":  # white-noise jerk
        return q * np.block([
            [dt ** 5 / 20 * I2, dt ** 4 / 8 * I2, dt ** 3 / 6 * I2],
            [dt ** 4 / 8 * I2, dt ** 3 / 3 * I2, dt ** 2 / 2 * I2],
            [dt ** 3 / 6 * I2, dt ** 2 / 2 * I2, dt * I2]])
    # white-noise acceleration (q in px^2/s^3)
    return np.block([
        [q * dt ** 3 / 3 * I2, q * dt ** 2 / 2 * I2, Z],
        [q * dt ** 2 / 2 * I2, q * dt * I2, Z],
        [Z, Z, 1e-3 * I2]])


H = np.hstack([np.eye(2), np.zeros((2, 4))])


class KF6:
    def __init__(self, model: str, q: float):
        self.model, self.q = model, q
        self.x = np.zeros(6)
        self.P = np.eye(6)

    def predict(self, dt: float, u: np.ndarray) -> None:
        F = _F(dt, self.model)
        self.x = F @ self.x
        self.x[:2] += u * dt  # known platform-rate input (from IMU)
        self.P = F @ self.P @ F.T + _Q(dt, self.model, self.q)

    def innov(self, z: np.ndarray, R: np.ndarray):
        nu = z - H @ self.x
        S = H @ self.P @ H.T + R
        return nu, S

    def update(self, z: np.ndarray, R: np.ndarray) -> float:
        nu, S = self.innov(z, R)
        Si = np.linalg.inv(S)
        K = self.P @ H.T @ Si
        self.x = self.x + K @ nu
        IKH = np.eye(6) - K @ H
        self.P = IKH @ self.P @ IKH.T + K @ R @ K.T  # Joseph form: numerically stable
        d2 = float(nu @ Si @ nu)
        return math.exp(-0.5 * d2) / (2 * math.pi * math.sqrt(max(np.linalg.det(S), 1e-12)))


class Estimator:
    """Common interface used by the PAT supervisor."""

    def __init__(self, kind: str, q_cv: float, q_ct: float, q_ca: float, meas_sigma: float,
                 adaptive_r: bool, gate: float = CHI2_2DOF_999):
        self.kind = kind
        self.meas_sigma = meas_sigma
        self.adaptive_r = adaptive_r
        self.gate = gate
        if kind == "imm":
            self.models = [KF6("cv", q_cv), KF6("ca", q_ca * 6.0), KF6("cv", q_ct * 25.0)]
            self.names = ["CV", "CA", "MNV"]
            self.mu = np.array([0.8, 0.1, 0.1])
            self.PI = np.array([[0.96, 0.02, 0.02], [0.03, 0.94, 0.03], [0.06, 0.04, 0.90]])
        else:
            self.models = [KF6("cv", q_cv)]
            self.names = ["CV"]
            self.mu = np.array([1.0])
            self.PI = np.array([[1.0]])
        self.initialised = False
        self.t = 0.0
        # before the jitter estimator has data, assume a moderate jitter (5 px) so early
        # measurements are not rejected; it converges within ~0.2 s of tracking
        self.R_adapt = np.eye(2) * (meas_sigma ** 2 + (25.0 if adaptive_r else 0.0))
        self.nis_hist: List[float] = []
        self.last_nis = 0.0
        self._zbuf: List[np.ndarray] = []
        self._d2: List[np.ndarray] = []
        self.jitter_sigma = 0.0

    # ------------------------------------------------------------------ #
    def init(self, z: np.ndarray, t: float, vel: Optional[np.ndarray] = None, pos_sigma: float = 6.0,
             vel_sigma: float = 200.0) -> None:
        for m in self.models:
            m.x = np.zeros(6)
            m.x[:2] = z
            if vel is not None:
                m.x[2:4] = vel
            m.P = np.diag([pos_sigma ** 2] * 2 + [vel_sigma ** 2] * 2 + [300.0 ** 2] * 2)
        self.mu = np.ones(len(self.models)) / len(self.models) if len(self.models) > 1 else np.array([1.0])
        self.t = t
        self.initialised = True
        self.nis_hist.clear()
        self._zbuf = []

    @property
    def x(self) -> np.ndarray:
        return sum(mu * m.x for mu, m in zip(self.mu, self.models))

    @property
    def P(self) -> np.ndarray:
        x = self.x
        return sum(mu * (m.P + np.outer(m.x - x, m.x - x)) for mu, m in zip(self.mu, self.models))

    def R(self) -> np.ndarray:
        return self.R_adapt if self.adaptive_r else np.eye(2) * self.meas_sigma ** 2

    def predict_to(self, t: float, u: np.ndarray) -> None:
        dt = t - self.t
        if dt <= 0:
            return
        if len(self.models) > 1:
            # IMM mixing
            c = self.PI.T @ self.mu
            mix = (self.PI * self.mu[:, None]) / np.maximum(c[None, :], 1e-12)
            xs = [m.x.copy() for m in self.models]
            Ps = [m.P.copy() for m in self.models]
            for j, m in enumerate(self.models):
                x0 = sum(mix[i, j] * xs[i] for i in range(len(xs)))
                P0 = sum(mix[i, j] * (Ps[i] + np.outer(xs[i] - x0, xs[i] - x0)) for i in range(len(xs)))
                m.x, m.P = x0, P0
            self.mu = c
        for m in self.models:
            m.predict(dt, u)
        self.t = t

    def predicted(self, dt_ahead: float = 0.0, u: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """Position/velocity extrapolated dt_ahead (no state change)."""
        x = self.x
        p = x[:2] + x[2:4] * dt_ahead + 0.5 * x[4:6] * dt_ahead ** 2 * (1.0 if self.kind == "imm" else 0.0)
        if u is not None:
            p = p + u * dt_ahead
        return p, x[2:4]

    def gate_and_score(self, z: np.ndarray) -> Tuple[float, float]:
        """Mahalanobis distance^2 of a candidate and its likelihood."""
        x, P = self.x, self.P
        S = P[:2, :2] + self.R()
        nu = z - x[:2]
        d2 = float(nu @ np.linalg.solve(S, nu))
        lik = math.exp(-0.5 * d2) / (2 * math.pi * math.sqrt(max(np.linalg.det(S), 1e-9)))
        return d2, lik

    def update(self, z: np.ndarray) -> float:
        R = self.R()
        HPH_prior = self.P[:2, :2].copy()
        S = HPH_prior + R
        nu = z - self.x[:2]
        nis = float(nu @ np.linalg.solve(S, nu))
        liks = np.array([m.update(z, R) for m in self.models])
        if len(self.models) > 1:
            mu = self.mu * liks
            s = mu.sum()
            self.mu = mu / s if s > 1e-300 else np.ones(len(self.models)) / len(self.models)
            self.mu = np.maximum(self.mu, 1e-4)
            self.mu /= self.mu.sum()
        if self.adaptive_r:
            # Jitter-aware measurement noise: camera jitter is white from frame to
            # frame while target motion is smooth, so the second difference of the
            # measurement sequence isolates it: var(z_k - 2 z_{k-1} + z_{k-2}) = 6 s_j^2
            # (+ a negligible a*dt^2 motion term). Robust (MAD) estimate over ~1 s.
            self._zbuf.append(z.copy())
            if len(self._zbuf) > 3:
                self._zbuf.pop(0)
            if len(self._zbuf) == 3:
                d2 = self._zbuf[2] - 2 * self._zbuf[1] + self._zbuf[0]
                self._d2.append(d2)
                if len(self._d2) > 30:
                    self._d2.pop(0)
            if len(self._d2) >= 5:
                D = np.array(self._d2)
                sj2 = (1.4826 * np.median(np.abs(D), axis=0)) ** 2 / 6.0
                self.jitter_sigma = float(np.sqrt(sj2.mean()))
                self.R_adapt = np.diag(self.meas_sigma ** 2 + np.clip(sj2, 0, 40.0 ** 2))
        self.last_nis = nis
        self.nis_hist.append(nis)
        if len(self.nis_hist) > 30:
            self.nis_hist.pop(0)
        return nis

    def pos_sigma(self) -> float:
        P = self.P[:2, :2]
        return float(math.sqrt(max(np.linalg.eigvalsh(P).max(), 0.0)))

    def consistency(self) -> float:
        """0..1 - how consistent recent innovations are with the filter model."""
        if not self.nis_hist:
            return 0.5
        m = float(np.mean(self.nis_hist[-10:]))
        return float(math.exp(-max(m - 2.0, 0.0) / 6.0))
