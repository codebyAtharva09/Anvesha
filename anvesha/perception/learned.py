"""Learned beacon heat-map network (BeaconNet) - ONNX Runtime inference.

BeaconNet is a ~4 k-parameter fully-convolutional network (dilated 3x3 convs)
trained only on physics-informed synthetic frames produced by this simulator
(tools/train_beaconnet.py). It outputs a per-pixel beacon-centre probability.

Roles:
  * Baseline C uses it as the primary detector (typical "AI detector" design).
  * ANVESHA uses it as a *verifier* on 32x32 patches around CFAR candidates,
    where it adds evidence against rain streaks, impulse clusters and
    look-alike distractors at < 1 ms per frame (measured in benchmarks).
If the model file is absent the system degrades gracefully to classical-only.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

try:
    import onnxruntime as ort
except Exception:  # pragma: no cover
    ort = None

DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "models" / "beaconnet.onnx"
PATCH = 32


def normalise(img: np.ndarray) -> Tuple[np.ndarray, float, float]:
    f = img.astype(np.float32)
    sub = f[::4, ::4]
    bg = float(np.median(sub))
    sd = float(1.4826 * np.median(np.abs(sub - bg))) + 1.0
    x = np.clip((f - bg) / (4.0 * sd), -2.0, 8.0)
    return x, bg, sd


class BeaconNet:
    def __init__(self, path: Optional[str | Path] = None, threads: int = 1):
        path = Path(path or os.environ.get("ANVESHA_MODEL", DEFAULT_MODEL))
        if ort is None or not path.exists():
            raise FileNotFoundError(f"BeaconNet model not available at {path}")
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        self.path = path

    def _run(self, x: np.ndarray) -> np.ndarray:
        return self.sess.run(None, {self.inp: x})[0]

    def heatmap(self, img: np.ndarray, scale: float = 0.5):
        """Full-frame heat-map (computed at `scale` resolution for speed)."""
        f = cv2.medianBlur(img, 3)
        x, bg, sd = normalise(f)
        if scale != 1.0:
            xs = cv2.resize(x, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        else:
            xs = x
        hm = self._run(xs[None, None].astype(np.float32))[0, 0]
        if scale != 1.0:
            hm = cv2.resize(hm, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
        return hm.astype(np.float32), x, bg, sd

    def verify(self, frame: np.ndarray, centres: Sequence[Tuple[float, float]], st=None) -> List[float]:
        """Score candidate centres. Each 32x32 patch is normalised with statistics of
        its own 64x64 neighbourhood (same scale as training), so cost is independent
        of the frame size."""
        if not centres:
            return []
        H, W = frame.shape
        batch = np.zeros((len(centres), 1, PATCH, PATCH), np.float32)
        h = PATCH // 2
        med = st is not None and st.sp_frac > 0.004
        for i, (u, v) in enumerate(centres):
            u, v = int(round(u)), int(round(v))
            X0, Y0 = max(u - 32, 0), max(v - 32, 0)
            X1, Y1 = min(u + 32, W), min(v + 32, H)
            if X1 - X0 < 8 or Y1 - Y0 < 8:
                continue
            win = frame[Y0:Y1, X0:X1]
            if med:
                win = cv2.medianBlur(np.ascontiguousarray(win), 3)
            x, _, _ = normalise(win)
            x0, y0 = u - h - X0, v - h - Y0
            xs0, ys0 = max(x0, 0), max(y0, 0)
            xs1, ys1 = min(x0 + PATCH, x.shape[1]), min(y0 + PATCH, x.shape[0])
            if xs1 > xs0 and ys1 > ys0:
                batch[i, 0, ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0] = x[ys0:ys1, xs0:xs1]
        hm = self._run(batch)[:, 0]
        c = slice(h - 3, h + 4)
        return [float(m[c, c].max()) for m in hm]


_cached: Optional[BeaconNet] = None


def load_default() -> Optional[BeaconNet]:
    global _cached
    if _cached is None:
        try:
            _cached = BeaconNet()
        except Exception:
            _cached = None
    return _cached
