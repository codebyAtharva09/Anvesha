"""Beacon detection and sub-pixel localisation.

Detectors (selectable, all return the same `Detection` records):
  threshold  - Baseline A: blur + global threshold + largest bright component
  blob       - Baseline B: median + adaptive threshold + size-filtered blobs
  cnn        - Baseline C: learned heat-map detector (ONNX) + CoG refinement
  mf_cfar    - noise-type-adaptive pre-filter, matched filter, CFAR test on a
               robust noise estimate (radar/star-tracker heritage)
  fusion     - ANVESHA: mf_cfar candidates scored by the CNN verifier and by
               shape features (rejects rain streaks, impulses, look-alikes)

The frame-level noise statistics (sigma, impulsive fraction, background) are
returned as well - they feed the disturbance-aware detection-probability model
used by the belief search (see search/belief.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class Detection:
    u: float
    v: float
    snr: float
    score: float           # 0..1 confidence that this is the beacon
    peak: float
    size: float            # estimated extent (px)
    elong: float           # elongation (1 = round/square)
    source: str = ""
    cnn: float = -1.0


@dataclass
class FrameStats:
    sigma: float = 1.0          # robust noise sigma of the matched-filter output
    pix_sigma: float = 1.0      # robust per-pixel noise sigma (after pre-filter)
    sp_frac: float = 0.0        # impulsive-noise fraction estimate
    background: float = 0.0
    contrast: float = 0.0       # brightest-candidate peak above background
    median_used: int = 0
    proc_ms: float = 0.0
    roi: Optional[Tuple[int, int, int, int]] = None


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def estimate_impulse_fraction(img: np.ndarray) -> float:
    sub = img[::3, ::3]
    return float(np.count_nonzero((sub == 0) | (sub == 255))) / sub.size


def robust_sigma(x: np.ndarray) -> float:
    sub = x[::2, ::2].ravel()
    med = np.median(sub)
    return float(1.4826 * np.median(np.abs(sub - med))) + 1e-3


def prefilter(img: np.ndarray, sp_frac: float) -> Tuple[np.ndarray, int]:
    """Adaptive impulse suppression: median size chosen from the measured
    impulsive fraction (switching-median idea, cf. adaptive median filters)."""
    k = 0
    if sp_frac > 0.12:
        k = 5
    elif sp_frac > 0.004:
        k = 3
    out = cv2.medianBlur(img, k) if k else img
    return out.astype(np.float32), k


def centroid(img: np.ndarray, u: float, v: float, size: float, bg: float, sigma: float,
             method: str = "iwcog", iters: int = 3) -> Tuple[float, float, float, float]:
    """Sub-pixel centre of a spot near (u, v).
    cog    - plain centre of gravity of pixels above a 3-sigma threshold
    iwcog  - iterative, windowed, background-subtracted, thresholded weighted CoG
    gauss  - separable 3-point log-parabola peak interpolation on a smoothed spot
    Returns (u, v, extent, elongation)."""
    H, W = img.shape
    half = int(math.ceil(max(size, 3.0) * 0.5 + 3))
    cu, cv_ = u, v
    ext, el = size, 1.0
    for _ in range(iters if method == "iwcog" else 1):
        x0, x1 = max(int(round(cu)) - half, 0), min(int(round(cu)) + half + 1, W)
        y0, y1 = max(int(round(cv_)) - half, 0), min(int(round(cv_)) + half + 1, H)
        if x1 - x0 < 3 or y1 - y0 < 3:
            return u, v, size, 1.0
        win = img[y0:y1, x0:x1].astype(np.float32) - bg
        if method == "gauss":
            sm = cv2.GaussianBlur(win, (0, 0), max(size / 4.0, 0.8))
            iy, ix = np.unravel_index(int(np.argmax(sm)), sm.shape)

            def interp(a, b, c):
                a, b, c = [math.log(max(q, 1e-3)) for q in (a, b, c)]
                d = a - 2 * b + c
                return 0.0 if abs(d) < 1e-9 else 0.5 * (a - c) / d
            dx = interp(sm[iy, ix - 1], sm[iy, ix], sm[iy, ix + 1]) if 0 < ix < sm.shape[1] - 1 else 0.0
            dy = interp(sm[iy - 1, ix], sm[iy, ix], sm[iy + 1, ix]) if 0 < iy < sm.shape[0] - 1 else 0.0
            return x0 + ix + dx, y0 + iy + dy, size, 1.0
        peak = float(win.max())
        thr = max(3.0 * sigma, 0.25 * peak) if method == "iwcog" else 3.0 * sigma
        wgt = win - thr
        wgt[wgt < 0] = 0
        s = float(wgt.sum())
        if s <= 1e-6:
            return u, v, size, 1.0
        ys, xs = np.mgrid[y0:y1, x0:x1]
        nu = float((wgt * xs).sum() / s)
        nv = float((wgt * ys).sum() / s)
        mxx = float((wgt * (xs - nu) ** 2).sum() / s)
        myy = float((wgt * (ys - nv) ** 2).sum() / s)
        mxy = float((wgt * (xs - nu) * (ys - nv)).sum() / s)
        tr, det = mxx + myy, mxx * myy - mxy * mxy
        disc = math.sqrt(max(tr * tr / 4 - det, 0.0))
        l1, l2 = tr / 2 + disc, max(tr / 2 - disc, 1e-3)
        el = math.sqrt(l1 / l2)
        ext = math.sqrt(12.0 * max(tr / 2, 1e-3))   # box of width a has variance a^2/12
        converged = abs(nu - cu) < 0.01 and abs(nv - cv_) < 0.01
        cu, cv_ = nu, nv
        if converged:
            break
    return cu, cv_, ext, el


# --------------------------------------------------------------------------- #
# detectors
# --------------------------------------------------------------------------- #
class Detector:
    def __init__(self, kind: str, cfar_k: float = 6.0, centroid_method: str = "iwcog",
                 cnn=None, use_verifier: bool = False):
        self.kind = kind
        self.k = cfar_k
        self.cm = centroid_method
        self.cnn = cnn
        self.use_verifier = use_verifier and cnn is not None

    # ------------------------------------------------------------------ #
    def detect(self, frame: np.ndarray, exp_size: float, roi: Optional[Tuple[float, float, float]] = None,
               max_n: int = 8) -> Tuple[List[Detection], FrameStats]:
        """frame: uint8 image. exp_size: expected beacon size in camera px.
        roi: optional (u, v, half) window to search (tracking mode)."""
        H, W = frame.shape
        off = (0, 0)
        img = frame
        if roi is not None:
            u, v, half = roi
            half = int(max(half, 3 * exp_size + 8))
            x0, x1 = int(max(u - half, 0)), int(min(u + half, W))
            y0, y1 = int(max(v - half, 0)), int(min(v + half, H))
            if x1 - x0 >= 16 and y1 - y0 >= 16:
                img = frame[y0:y1, x0:x1]
                off = (x0, y0)
        fn = {"threshold": self._threshold, "blob": self._blob, "cnn": self._cnn,
              "mf_cfar": self._mf_cfar, "fusion": self._mf_cfar}[self.kind]
        dets, st = fn(img, exp_size, max_n)
        for d in dets:
            d.u += off[0]
            d.v += off[1]
        if roi is not None and img is not frame:
            st.roi = (off[0], off[1], img.shape[1], img.shape[0])
        if self.kind == "fusion" and self.use_verifier and dets:
            self._verify(frame, dets, exp_size, st)
        dets.sort(key=lambda d: -d.score)
        return dets[:max_n], st

    # ---- Baseline A --------------------------------------------------- #
    def _threshold(self, img, exp_size, max_n):
        f = cv2.GaussianBlur(img, (3, 3), 0).astype(np.float32)
        mu, sd = float(f.mean()), float(f.std()) + 1e-3
        thr = max(mu + 5 * sd, mu + 40.0, 0.5 * float(f.max()))
        mask = (f > thr).astype(np.uint8)
        n, lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
        st = FrameStats(sigma=sd, pix_sigma=sd, background=mu)
        if n <= 1:
            return [], st
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        u, v, ext, el = centroid(f, cents[i][0], cents[i][1], exp_size, mu, sd, "cog")
        return [Detection(u, v, (float(f.max()) - mu) / sd, 0.6, float(f.max()), ext, el, "threshold")], st

    # ---- Baseline B --------------------------------------------------- #
    def _blob(self, img, exp_size, max_n):
        sp = estimate_impulse_fraction(img)
        f = cv2.medianBlur(img, 3)
        bg = cv2.blur(f, (31, 31)).astype(np.float32)
        r = f.astype(np.float32) - bg
        sd = robust_sigma(r)
        mask = (r > max(5 * sd, 15.0)).astype(np.uint8)
        n, lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
        st = FrameStats(sigma=sd, pix_sigma=sd, sp_frac=sp, background=float(bg.mean()), median_used=3)
        out = []
        amin = max((0.5 * exp_size) ** 2, 4)
        amax = (2.5 * exp_size) ** 2 + 20
        for i in range(1, n):
            a = stats[i, cv2.CC_STAT_AREA]
            if amin <= a <= amax:
                u, v, ext, el = centroid(r, cents[i][0], cents[i][1], exp_size, 0.0, sd, "cog")
                pk = float(r[int(stats[i, 1]):int(stats[i, 1] + stats[i, 3]), int(stats[i, 0]):int(stats[i, 0] + stats[i, 2])].max())
                out.append(Detection(u, v, pk / sd, min(1.0, a / (exp_size ** 2 + 1)), pk, ext, el, "blob"))
        out.sort(key=lambda d: -d.snr)
        return out[:max_n], st

    # ---- Baseline C --------------------------------------------------- #
    def _cnn(self, img, exp_size, max_n):
        if self.cnn is None:
            return self._blob(img, exp_size, max_n)
        sp = estimate_impulse_fraction(img)
        hm, norm_img, bg, sd = self.cnn.heatmap(img)
        st = FrameStats(sigma=sd, pix_sigma=sd, sp_frac=sp, background=bg)
        dil = cv2.dilate(hm, np.ones((5, 5), np.uint8))
        ys, xs = np.nonzero((hm >= dil) & (hm > 0.3))
        out = []
        f = cv2.medianBlur(img, 3).astype(np.float32)
        for y, x in sorted(zip(ys, xs), key=lambda p: -hm[p[0], p[1]])[:max_n]:
            u, v, ext, el = centroid(f, float(x), float(y), exp_size, bg, sd, "cog")
            out.append(Detection(u, v, float(hm[y, x]) * 10, float(hm[y, x]), float(f[y, x]) - bg, ext, el, "cnn",
                                 float(hm[y, x])))
        return out, st

    # ---- ANVESHA matched filter + CFAR ------------------------------- #
    def _mf_cfar(self, img, exp_size, max_n):
        sp = estimate_impulse_fraction(img)
        f, k = prefilter(img, sp)
        # background: large box mean on a 4x decimated copy (fast, removes haze veil / gradients)
        h, w = f.shape
        small = cv2.resize(f, (max(w // 4, 1), max(h // 4, 1)), interpolation=cv2.INTER_AREA)
        bk = int(max(9, 2 * exp_size)) | 1
        bgs = cv2.blur(small, (bk, bk))
        bg = cv2.resize(bgs, (w, h), interpolation=cv2.INTER_LINEAR)
        r = f - bg
        pix_sd = robust_sigma(r)
        m = int(max(3, round(exp_size))) | 1
        mf = cv2.boxFilter(r, -1, (m, m), normalize=True)
        # noise floor: 8-bit quantisation (1/sqrt(12) DN per pixel) averaged over the m x m window
        sd = max(robust_sigma(mf), 0.29 / m)
        snr = mf / sd
        st = FrameStats(sigma=sd, pix_sigma=pix_sd, sp_frac=sp, background=float(np.median(bgs)), median_used=k)
        dil = cv2.dilate(snr, np.ones((m + 2, m + 2), np.uint8))
        ys, xs = np.nonzero((snr >= dil) & (snr > self.k))
        if len(xs) == 0:
            return [], st
        order = np.argsort(-snr[ys, xs])[: max_n * 3]
        out = []
        for j in order:
            y, x = int(ys[j]), int(xs[j])
            if r[y, x] < 3.0:   # below any physically meaningful beacon contrast
                continue
            u, v, ext, el = centroid(r, float(x), float(y), exp_size, 0.0, pix_sd, self.cm)
            s = float(snr[y, x])
            # shape score: compact, roughly the expected size, not elongated (rain streaks)
            size_ok = math.exp(-0.5 * (math.log(max(ext, 0.5) / max(exp_size, 1.0)) / 0.5) ** 2)
            round_ok = math.exp(-max(el - 1.3, 0.0) / 0.6)
            score = (1 - math.exp(-(s - self.k + 1) / 4.0)) * (0.35 + 0.65 * size_ok * round_ok)
            out.append(Detection(u, v, s, float(np.clip(score, 0, 1)), float(r[y, x]), ext, el, "mf_cfar"))
            if len(out) >= max_n:
                break
        st.contrast = out[0].peak if out else 0.0
        return out, st

    def _verify(self, frame, dets, exp_size, st):
        """CNN verifier on 32x32 patches: fuse learned evidence with the CFAR score."""
        probs = self.cnn.verify(frame, [(d.u, d.v) for d in dets], st)
        for d, p in zip(dets, probs):
            d.cnn = float(p)
            # veto-type fusion: the learned verifier can lower confidence (clutter, streaks,
            # impulse clusters) but cannot rescue a candidate the physics-based tests rejected
            d.score = float(np.clip(d.score * (0.4 + 0.6 * p), 0, 1))
