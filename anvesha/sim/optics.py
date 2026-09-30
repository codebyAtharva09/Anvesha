"""Image formation for the virtual focal-plane-array camera.

* The virtual *environment* (screen) is a 2000 x 2000 radiance map: dark sky
  background, optional stars / clutter / static beacon look-alike distractors.
* The *beacon* is rendered analytically (box of the configured size convolved
  with a Gaussian PSF and integrated over the pixel) directly in camera
  coordinates, so its true sub-pixel centre is known exactly - this is the
  ground truth for the centroiding-error metric.
* Zoom (adaptive FOV) maps z x z screen pixels onto one camera pixel.
  Modelling assumption: image irradiance of extended objects is preserved
  (constant f-number zoom), so a wider FOV makes the beacon smaller - and its
  matched-filter SNR lower - which is the real acquisition trade-off.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import cv2
import numpy as np
from scipy.special import erf


def _box_profile(coords: np.ndarray, c: float, half: float, sigma: float) -> np.ndarray:
    """1-D box [c-half, c+half] convolved with N(0, sigma^2), sampled at pixel
    centres (sigma already includes the pixel-integration term)."""
    s = math.sqrt(2.0) * sigma
    return 0.5 * (erf((coords - (c - half)) / s) - erf((coords - (c + half)) / s))


def render_spot(img: np.ndarray, u0: float, v0: float, size: float, peak: float,
                psf_sigma: float, shape: str = "square") -> None:
    """Add a beacon centred at (u0, v0) (camera px, continuous) into `img` in place."""
    H, W = img.shape
    sig = math.sqrt(psf_sigma ** 2 + 1.0 / 12.0)
    r = int(math.ceil(size / 2 + 4 * sig + 1))
    x0, x1 = int(math.floor(u0)) - r, int(math.floor(u0)) + r + 1
    y0, y1 = int(math.floor(v0)) - r, int(math.floor(v0)) + r + 1
    if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
        return
    xs = np.arange(max(x0, 0), min(x1, W), dtype=np.float32)
    ys = np.arange(max(y0, 0), min(y1, H), dtype=np.float32)
    if shape == "gaussian" or size < 1.5:
        s2 = max(size / 2.355, 0.5) ** 2 + sig ** 2
        px = np.exp(-0.5 * (xs - u0) ** 2 / s2)
        py = np.exp(-0.5 * (ys - v0) ** 2 / s2)
        patch = np.outer(py, px)
    elif shape == "circle":
        # circle approximated by a rotationally symmetric super-Gaussian
        X, Y = np.meshgrid(xs - u0, ys - v0)
        R = np.sqrt(X * X + Y * Y)
        patch = 0.5 * (1 - erf((R - size / 2) / (math.sqrt(2) * sig)))
    else:
        px = _box_profile(xs, u0, size / 2, sig)
        py = _box_profile(ys, v0, size / 2, sig)
        patch = np.outer(py, px)
    img[int(ys[0]):int(ys[-1]) + 1, int(xs[0]):int(xs[-1]) + 1] += (peak * patch).astype(np.float32)


class Scene:
    """Static part of the virtual environment (screen radiance map)."""

    def __init__(self, W: int, H: int, kind: str, level: float, n_stars: int, n_distractors: int,
                 distractor_level: float, target_size: float, rng: np.random.Generator):
        self.W, self.H = W, H
        self.kind = kind
        base = np.full((H, W), float(level), dtype=np.float32)
        if kind in ("clutter", "dark_sky"):
            # smooth low-frequency sky gradient / thin clouds
            amp = 3.0 if kind == "dark_sky" else 25.0
            small = rng.standard_normal((H // 100 + 2, W // 100 + 2)).astype(np.float32)
            smooth = cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)
            base += amp * smooth
        self.distractors = []
        if kind in ("starfield", "clutter"):
            for _ in range(n_stars):
                u, v = rng.uniform(0, W), rng.uniform(0, H)
                render_spot(base, u, v, 1.0, float(rng.uniform(15, 70)), 0.9, "gaussian")
        for _ in range(n_distractors):
            u, v = rng.uniform(100, W - 100), rng.uniform(100, H - 100)
            sz = float(rng.uniform(0.6, 1.4) * target_size)
            render_spot(base, u, v, sz, distractor_level * float(rng.uniform(0.7, 1.1)), 0.8, "square")
            self.distractors.append((u, v, sz))
        self.levels: Dict[int, np.ndarray] = {1: base}

    def level(self, zoom: float) -> np.ndarray:
        """Background pre-integrated for a zoom factor (area-averaged)."""
        z = int(round(zoom))
        if z not in self.levels:
            self.levels[z] = cv2.resize(self.levels[1], (self.W // z, self.H // z), interpolation=cv2.INTER_AREA)
        return self.levels[z]

    def crop(self, cx: float, cy: float, zoom: float, w: int, h: int) -> np.ndarray:
        """Camera-sized crop centred on screen point (cx, cy) at the given zoom."""
        z = int(round(zoom))
        src = self.level(z)
        # camera pixel (u,v) -> level pixel: (cx/z - w/2 + u, cy/z - h/2 + v)
        tx, ty = cx / z - w / 2.0, cy / z - h / 2.0
        M = np.array([[1, 0, tx], [0, 1, ty]], dtype=np.float32)
        return cv2.warpAffine(src, M, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_REFLECT)
