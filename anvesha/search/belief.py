"""Belief-driven acquisition and re-acquisition (ANVESHA's search engine).

A discrete probability map b(x) over the virtual screen is propagated with a
target-motion model and updated with *negative information* every frame in
which the beacon is not detected inside the camera footprint:

    b(x) <- b(x) * (1 - Pd(zoom, conditions) * cover(x))      (Bayes, miss)

The next look (pointing + zoom level) maximises the detection-probability
rate  Pd(z) * mass(footprint_z(p)) / (slew_time(p) + zoom_time + dwell).
Pd(z) is a *disturbance-aware* sensor model: predicted matched-filter SNR at
that zoom from the currently measured noise, compared with the CFAR
threshold. In clear air the planner prefers a wide FOV; in fog / heavy noise,
where a small beacon would be missed, it prefers the narrow FOV.

The same machinery performs re-acquisition: on track loss the belief is
initialised from the estimator's predicted mean/covariance, so the camera
looks first where the beacon most probably is.

Classical optimal-search theory (Koopman; Stone) and information-driven PTZ
sensor management are the foundations; see docs/literature for references.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np
from scipy.stats import norm


@dataclass
class LookPlan:
    xy: np.ndarray        # desired boresight (screen px)
    zoom: float
    score: float
    mass: float
    pd: float
    eta_s: float


CONTRAST_FACTORS = np.array([1.0, 0.5, 0.25, 0.12])   # beacon contrast hypotheses x nominal
CONTRAST_PRIOR = np.array([0.4, 0.3, 0.2, 0.1])


class BeliefMap:
    """Joint belief over beacon position AND detectability.

    B[k, y, x] = P(beacon in cell (x, y) and its contrast = CONTRAST_FACTORS[k] x nominal).
    A missed look is evidence about both: in fog, repeated misses with a wide FOV
    shift probability mass to the low-contrast hypotheses, for which the wide FOV
    is nearly blind - so the planner switches to the narrow FOV automatically."""

    def __init__(self, W: int, H: int, cell: int, speed_prior: float):
        self.W, self.H, self.cell = W, H, cell
        self.nx, self.ny = int(math.ceil(W / cell)), int(math.ceil(H / cell))
        self.speed_prior = speed_prior
        self.K = len(CONTRAST_FACTORS)
        self.B = np.zeros((self.K, self.ny, self.nx), np.float64)
        self.adv = np.zeros(2)
        self.reset_uniform()

    @property
    def b(self) -> np.ndarray:
        return self.B.sum(0)

    @b.setter
    def b(self, val: np.ndarray) -> None:  # used when the platform shifts the whole map
        tot = self.B.sum(0)
        ratio = np.divide(val, tot, out=np.ones_like(val), where=tot > 0)
        self.B *= ratio[None]

    def contrast_posterior(self) -> np.ndarray:
        w = self.B.sum((1, 2))
        return w / max(w.sum(), 1e-300)

    def reset_uniform(self, weights: Optional[np.ndarray] = None) -> None:
        w = CONTRAST_PRIOR if weights is None else weights
        w = w / w.sum()
        for k in range(self.K):
            self.B[k] = w[k] / (self.nx * self.ny)
        self.adv[:] = 0

    def reset_gaussian(self, mean: np.ndarray, cov: np.ndarray, vel: Optional[np.ndarray] = None,
                       uniform_mix: float = 0.03, weights: Optional[np.ndarray] = None) -> None:
        xs = (np.arange(self.nx) + 0.5) * self.cell
        ys = (np.arange(self.ny) + 0.5) * self.cell
        X, Y = np.meshgrid(xs, ys)
        d = np.stack([X - mean[0], Y - mean[1]], -1)
        cov = cov + np.eye(2) * (self.cell ** 2) / 4
        ci = np.linalg.inv(cov)
        m = np.einsum("...i,ij,...j->...", d, ci, d)
        g = np.exp(-0.5 * m)
        g /= g.sum()
        g = (1 - uniform_mix) * g + uniform_mix / g.size
        w = CONTRAST_PRIOR if weights is None else weights
        w = w / w.sum()
        self.B = w[:, None, None] * g[None]
        self.adv = np.zeros(2) if vel is None else np.asarray(vel, float)

    def _norm(self) -> None:
        self.B = np.maximum(self.B, 0)
        s = self.B.sum()
        if s <= 1e-300:
            self.reset_uniform()
        else:
            self.B /= s

    def predict(self, dt: float) -> None:
        """Motion model: advection by the last known velocity (decaying) and
        diffusion with the prior speed (applied to every contrast layer)."""
        if np.linalg.norm(self.adv) > 1e-6:
            shift = self.adv * dt / self.cell
            M = np.float32([[1, 0, shift[0]], [0, 1, shift[1]]])
            for k in range(self.K):
                self.B[k] = cv2.warpAffine(self.B[k].astype(np.float32), M, (self.nx, self.ny),
                                           flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            self.adv *= math.exp(-dt / 2.0)
        s = self.speed_prior * dt / self.cell
        if s > 0.05:
            for k in range(self.K):
                self.B[k] = cv2.GaussianBlur(self.B[k], (0, 0), s, borderType=cv2.BORDER_REFLECT)
        self._norm()

    def _footprint_cover(self, xy: np.ndarray, half: np.ndarray) -> np.ndarray:
        x0, x1 = xy[0] - half[0], xy[0] + half[0]
        y0, y1 = xy[1] - half[1], xy[1] + half[1]
        cx = np.arange(self.nx) * self.cell
        cy = np.arange(self.ny) * self.cell
        ox = np.clip(np.minimum(cx + self.cell, x1) - np.maximum(cx, x0), 0, self.cell) / self.cell
        oy = np.clip(np.minimum(cy + self.cell, y1) - np.maximum(cy, y0), 0, self.cell) / self.cell
        return np.outer(oy, ox)

    def miss_update(self, xy: np.ndarray, half: np.ndarray, pd) -> None:
        """Bayes update for 'looked here, saw nothing'. pd: scalar or per-hypothesis array."""
        cover = self._footprint_cover(xy, half)
        pd = np.broadcast_to(np.asarray(pd, float), (self.K,))
        self.B *= (1.0 - pd[:, None, None] * cover[None])
        self._norm()

    def mass_in(self, xy: np.ndarray, half: np.ndarray) -> np.ndarray:
        cover = self._footprint_cover(xy, half)
        return (self.B * cover[None]).sum((1, 2))

    def entropy(self) -> float:
        p = self.B[self.B > 0]
        return float(-(p * np.log(p)).sum())

    def peak(self) -> np.ndarray:
        b = self.b
        iy, ix = np.unravel_index(int(np.argmax(b)), b.shape)
        return np.array([(ix + 0.5) * self.cell, (iy + 0.5) * self.cell])


class DetectionModel:
    """Pd(zoom, contrast hypothesis) from the measured matched-filter noise.
    The nominal (clear-air) beacon contrast is a design parameter of the remote
    terminal; the actual contrast under the current atmosphere is unknown and is
    carried as hypotheses in the joint belief."""

    def __init__(self, cfar_k: float, size_px: float, nominal_contrast: float):
        self.k = cfar_k
        self.size = size_px
        self.nominal = nominal_contrast
        self.contrast = nominal_contrast * 0.5   # last measured beacon contrast (after a detection)
        self.pix_sigma = 3.0
        self.impulse = 0.0

    def observe_noise(self, pix_sigma: float, sp_frac: float) -> None:
        a = 0.2
        self.pix_sigma = (1 - a) * self.pix_sigma + a * max(pix_sigma, 0.5)
        self.impulse = (1 - a) * self.impulse + a * sp_frac

    def observe_beacon(self, contrast: float) -> None:
        if contrast > 0:
            self.contrast = 0.7 * self.contrast + 0.3 * contrast

    def snr(self, zoom: float, contrast: Optional[float] = None) -> float:
        c = self.contrast if contrast is None else contrast
        s = self.size / zoom
        m = max(3, int(round(s)) | 1)
        fill = min(1.0, (s / m) ** 2) * (0.85 if s >= 3 else 0.6)
        return c * fill * m / self.pix_sigma

    def pd_vec(self, zoom: float) -> np.ndarray:
        """Pd for every contrast hypothesis."""
        snr = np.array([self.snr(zoom, self.nominal * f) for f in CONTRAST_FACTORS])
        p = norm.cdf(snr - self.k)
        return np.clip(p * (1 - 0.5 * self.impulse), 0.0, 0.98)

    def pd(self, zoom: float, weights: Optional[np.ndarray] = None) -> float:
        """Expected Pd (averaged over contrast hypotheses with `weights`), or the
        Pd at the last measured contrast when no weights are given."""
        if weights is not None:
            return float((self.pd_vec(zoom) * weights).sum())
        p = float(norm.cdf(self.snr(zoom) - self.k))
        return float(np.clip(p * (1 - 0.5 * self.impulse), 0.0, 0.98))

    def weights_from_measured(self) -> np.ndarray:
        """Contrast-hypothesis weights centred on the last measured contrast (used to seed re-acquisition)."""
        r = np.log(np.maximum(self.contrast, 1e-3) / (self.nominal * CONTRAST_FACTORS))
        w = np.exp(-0.5 * (r / 0.5) ** 2) + 0.02
        return w / w.sum()


class BeliefPlanner:
    def __init__(self, bm: BeliefMap, dm: DetectionModel, fov_half_px: np.ndarray, zooms: List[float],
                 max_rate_px: np.ndarray, zoom_time: float, frame_dt: float, dwell_frames: int, allow_zoom: bool):
        self.bm, self.dm = bm, dm
        self.fov_half = fov_half_px.astype(float)
        self.zooms = zooms if allow_zoom else [1.0]
        self.max_rate = max_rate_px
        self.zoom_time = zoom_time
        self.frame_dt = frame_dt
        self.dwell = dwell_frames * frame_dt
        self.plan: Optional[LookPlan] = None
        stride = 2
        xs = (np.arange(0, bm.nx, stride) + 0.5) * bm.cell
        ys = (np.arange(0, bm.ny, stride) + 0.5) * bm.cell
        X, Y = np.meshgrid(xs, ys)
        self.cand = np.stack([X.ravel(), Y.ravel()], 1)

    def _masses(self, half: np.ndarray) -> np.ndarray:
        """Per-hypothesis belief mass inside a footprint centred at every
        candidate (box filter = summed-area evaluation). Shape (K, n_cand)."""
        c = self.bm.cell
        kx = max(int(round(2 * half[0] / c)), 1)
        ky = max(int(round(2 * half[1] / c)), 1)
        ix = np.clip((self.cand[:, 0] / c).astype(int), 0, self.bm.nx - 1)
        iy = np.clip((self.cand[:, 1] / c).astype(int), 0, self.bm.ny - 1)
        out = []
        for k in range(self.bm.K):
            box = cv2.boxFilter(self.bm.B[k], -1, (kx, ky), normalize=False, borderType=cv2.BORDER_CONSTANT)
            out.append(box[iy, ix])
        return np.array(out)

    def expected_pd(self, zoom: float) -> float:
        return self.dm.pd(zoom, self.bm.contrast_posterior())

    def choose(self, bore: np.ndarray, zoom_now: float) -> LookPlan:
        best = None
        for z in self.zooms:
            half = self.fov_half * z
            pdv = self.dm.pd_vec(z)
            masses = self._masses(half)
            gain = (pdv[:, None] * masses).sum(0)          # P(detect | look at candidate with zoom z)
            d = np.abs(self.cand - bore[None, :])
            t_slew = np.max(d / self.max_rate[None, :], axis=1)
            t = t_slew + (self.zoom_time if abs(z - zoom_now) > 1e-6 else 0.0) + self.dwell
            score = gain / t
            i = int(np.argmax(score))
            if best is None or score[i] > best.score:
                best = LookPlan(self.cand[i].copy(), z, float(score[i]), float(masses[:, i].sum()),
                                float(gain[i] / max(masses[:, i].sum(), 1e-12)), float(t[i]))
        # hysteresis: keep the current plan unless clearly beaten (avoids dithering)
        if self.plan is not None:
            cur_half = self.fov_half * self.plan.zoom
            m = self.bm.mass_in(self.plan.xy, cur_half)
            cur_gain = float((self.dm.pd_vec(self.plan.zoom) * m).sum())
            dist = np.abs(self.plan.xy - bore)
            cur_t = float(np.max(dist / self.max_rate)) + self.dwell
            cur_score = cur_gain / cur_t
            if m.sum() > 0.02 and cur_score * 1.25 >= best.score and np.max(dist) > 4:
                self.plan.score = cur_score
                return self.plan
        self.plan = best
        return best


class PatternSearch:
    """Baseline square-spiral / raster search at the base FOV (no belief)."""

    def __init__(self, kind: str, center: np.ndarray, fov_half: np.ndarray, W: int, H: int, overlap: float = 0.8):
        self.kind = kind
        self.pts: List[np.ndarray] = []
        sx, sy = 2 * fov_half[0] * overlap, 2 * fov_half[1] * overlap
        if kind == "raster":
            ys = np.arange(fov_half[1], H, sy)
            for r, y in enumerate(ys):
                xs = np.arange(fov_half[0], W, sx)
                if r % 2:
                    xs = xs[::-1]
                self.pts += [np.array([x, y]) for x in xs]
        else:  # square spiral outward from the centre
            p = center.astype(float).copy()
            self.pts.append(p.copy())
            dirs = [np.array([1, 0]), np.array([0, 1]), np.array([-1, 0]), np.array([0, -1])]
            leg, k = 1, 0
            max_leg = int(max(W / sx, H / sy)) * 2 + 4
            while len(self.pts) < 400 and leg <= max_leg:
                for _ in range(2):
                    for _ in range(leg):
                        p = p + dirs[k % 4] * np.array([sx, sy])
                        if -fov_half[0] <= p[0] <= W + fov_half[0] and -fov_half[1] <= p[1] <= H + fov_half[1]:
                            self.pts.append(p.copy())
                    k += 1
                leg += 1
        self.i = 0

    def target(self, bore: np.ndarray, tol: float = 12.0) -> np.ndarray:
        if not self.pts:
            return bore
        tgt = self.pts[self.i % len(self.pts)]
        if np.max(np.abs(tgt - bore)) < tol:
            self.i += 1
            tgt = self.pts[self.i % len(self.pts)]
        return tgt
