"""Pan/tilt control laws (outputs are gimbal *rate* commands, screen px/s).

PIDController        - Baselines: PID on the image-plane centroid error.
PredictiveController - ANVESHA: estimator-based tracking with
    * target-rate feed-forward from the IMM velocity,
    * platform-rate feed-forward from the IMU (disturbance feed-forward),
    * latency compensation (predict to t + tau_total),
    * proportional correction on the predicted pointing error,
    * time-optimal (sqrt) slew shaping for large errors -> no overshoot at the
      rate/acceleration limits, no integrator -> no wind-up.
All commands are bounded by the configured pan/tilt rate limits (PS #13/#14).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np


def slew_profile(err: np.ndarray, max_rate: np.ndarray, max_acc: float, kp: float) -> np.ndarray:
    """Rate that brings the error to zero without overshoot: min(kp*e, sqrt(2 a |e|))."""
    lin = kp * err
    sq = np.sign(err) * np.sqrt(2.0 * 0.8 * max_acc * np.abs(err))
    out = np.where(np.abs(lin) < np.abs(sq), lin, sq)
    return np.clip(out, -max_rate, max_rate)


class PIDController:
    def __init__(self, kp: float, ki: float, kd: float, max_rate: np.ndarray, max_acc: float):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.max_rate, self.max_acc = max_rate, max_acc
        self.i = np.zeros(2)
        self.prev: Optional[np.ndarray] = None

    def reset(self):
        self.i[:] = 0
        self.prev = None

    def track(self, err_px: np.ndarray, dt: float) -> np.ndarray:
        """err_px: target minus boresight (gimbal-frame px)."""
        d = np.zeros(2) if self.prev is None else (err_px - self.prev) / max(dt, 1e-3)
        self.prev = err_px.copy()
        self.i += err_px * dt
        cmd = self.kp * err_px + self.ki * self.i + self.kd * d
        sat = np.clip(cmd, -self.max_rate, self.max_rate)
        # conditional-integration anti-wind-up: undo integration on saturated axes
        wind = (cmd != sat) & (np.sign(err_px) == np.sign(cmd))
        self.i[wind] -= err_px[wind] * dt
        return sat

    def slew(self, err_px: np.ndarray) -> np.ndarray:
        return slew_profile(err_px, self.max_rate, self.max_acc, 3.0)


class PredictiveController:
    def __init__(self, kp: float, max_rate: np.ndarray, max_acc: float, latency: float,
                 use_ff: bool = True, use_imu: bool = True, use_latency: bool = True):
        self.kp = kp
        self.max_rate, self.max_acc = max_rate, max_acc
        self.latency = latency if use_latency else 0.0
        self.use_ff, self.use_imu = use_ff, use_imu
        self.last_cmd = np.zeros(2)

    def reset(self):
        self.last_cmd[:] = 0

    def track(self, x_g: np.ndarray, v_target: np.ndarray, gimbal: np.ndarray, gimbal_rate: np.ndarray,
              imu_rate: Optional[np.ndarray]) -> np.ndarray:
        """x_g: estimated gimbal-frame target position at *now*; v_target: target
        velocity estimate (world); imu_rate: platform LOS rate (or None)."""
        tau = self.latency
        w = imu_rate if (imu_rate is not None and self.use_imu) else np.zeros(2)
        v_rel = (v_target if self.use_ff else np.zeros(2)) - w
        x_future = x_g + v_rel * tau
        g_future = gimbal + gimbal_rate * tau
        err = x_future - g_future
        ff = v_rel if (self.use_ff or self.use_imu) else np.zeros(2)
        cmd = ff + slew_profile(err, self.max_rate * 2.0, self.max_acc, self.kp)
        cmd = np.clip(cmd, -self.max_rate, self.max_rate)
        self.last_cmd = cmd
        return cmd

    def slew(self, err_px: np.ndarray, imu_rate: Optional[np.ndarray] = None) -> np.ndarray:
        w = imu_rate if (imu_rate is not None and self.use_imu) else np.zeros(2)
        return np.clip(slew_profile(err_px, self.max_rate, self.max_acc, 4.0) - w, -self.max_rate, self.max_rate)
