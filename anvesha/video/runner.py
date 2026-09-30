"""Benchmark-2 mode: evaluator .mp4 input, PTZ camera bypassed.

The PS states that evaluators will supply 30 fps videos covering the complete
screen with noise and a moving beacon, and that the software must take the
video as the input to the coarse-pointing system. Two sub-modes:

  fullframe  (default) the whole frame is the sensor. Acquisition runs the
             detector on the full frame; once locked, only an ROI around the
             IMM prediction is processed (fast), with a full-frame fallback
             when the beacon is not found. Every frame logs the RAW measured
             centroid (what "centroiding error" should be computed on) and the
             filtered estimate separately.
  viewport   emulated PTZ over the video: a 640x480 window is steered by the
             same predictive controller with rate limits (demonstrates the
             closed loop on recorded data).

If a truth CSV (frame, x, y) is given, centroiding error is computed.
"""
from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

from ..estimation.filters import Estimator
from ..perception.detectors import Detector
from ..perception.learned import load_default


def load_truth(path: Optional[str]) -> Dict[int, tuple]:
    if not path:
        return {}
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("visible", "1") in ("0", "False", "false"):
                continue
            out[int(r["frame"])] = (float(r["x"]), float(r["y"]))
    return out


class VideoTracker:
    def __init__(self, beacon_size: float = 10.0, detector: str = "fusion", cfar_k: float = 6.0,
                 roi_half: float = 60.0, coast_frames: int = 15):
        cnn = load_default() if detector in ("fusion", "cnn") else None
        self.det = Detector(detector, cfar_k, "iwcog", cnn, detector == "fusion")
        self.est = Estimator("imm", 800.0, 300.0, 2000.0, 0.7, True)
        self.size = beacon_size
        self.roi_half = roi_half
        self.coast_frames = coast_frames
        self.mode = "SEARCH"
        self.miss = 0
        self.pending: List[np.ndarray] = []

    def process(self, gray: np.ndarray, t: float):
        t0 = time.perf_counter()
        z = None
        chosen = None
        if self.mode in ("TRACK", "COAST") and self.est.initialised:
            self.est.predict_to(t, np.zeros(2))
            p = self.est.x[:2]
            half = max(self.roi_half, 4 * self.est.pos_sigma() + 3 * self.size)
            dets, st = self.det.detect(gray, self.size, (p[0], p[1], half))
            best, bs = None, -1
            for d in dets:
                # the ROI already bounds the search; inside it, rank by confidence x gate likelihood
                d2, _ = self.est.gate_and_score(np.array([d.u, d.v]))
                sc = d.score * math.exp(-0.5 * d2 / (4.0 * self.est.gate))
                if d.score > 0.35 and sc > bs:
                    best, bs = d, sc
            if best is None:
                dets, st = self.det.detect(gray, self.size, None)
                for d in dets:
                    if d.score >= 0.6 and np.linalg.norm(np.array([d.u, d.v]) - p) < 40 + 30 * self.miss:
                        best = d
                        self.est.init(np.array([d.u, d.v]), t, None, 2.0, 300.0)
                        break
            chosen = best
            if chosen is not None:
                z = np.array([chosen.u, chosen.v])
                self.est.update(z)
                self.mode, self.miss = "TRACK", 0
            else:
                self.miss += 1
                self.mode = "COAST"
                if self.miss > self.coast_frames:
                    self.mode = "SEARCH"
                    self.est.initialised = False
        else:
            dets, st = self.det.detect(gray, self.size, None)
            cand = [d for d in dets if d.score >= 0.45]
            if cand:
                chosen = cand[0]
                z = np.array([chosen.u, chosen.v])
                if self.pending and np.linalg.norm(z - self.pending[-1]) < 60:
                    self.est.init(z, t, None, 2.0, 300.0)
                    self.mode = "TRACK"
                    self.pending = []
                else:
                    self.pending = [z]
                    self.mode = "ACQUIRE"
            else:
                self.pending = []
                self.mode = "SEARCH"
        ms = (time.perf_counter() - t0) * 1000
        est = self.est.x[:2].copy() if self.est.initialised else None
        return self.mode, chosen, z, est, ms


def run_video(path: str, out_dir: str, truth_csv: Optional[str] = None, beacon_size: float = 10.0,
              detector: str = "fusion", max_frames: Optional[int] = None, fps_hint: float = 30.0) -> Dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise FileNotFoundError(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or fps_hint
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    truth = load_truth(truth_csv)
    vt = VideoTracker(beacon_size, detector)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    k = 0
    t_decode = 0.0
    wall0 = time.perf_counter()
    while True:
        a = time.perf_counter()
        ok, fr = cap.read()
        if not ok or (max_frames and k >= max_frames):
            break
        gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY) if fr.ndim == 3 else fr
        t_decode += time.perf_counter() - a
        t = k / fps
        mode, ch, z, est, ms = vt.process(gray, t)
        tr = truth.get(k)
        ce = math.hypot(z[0] - tr[0], z[1] - tr[1]) if (z is not None and tr is not None) else float("nan")
        ee = math.hypot(est[0] - tr[0], est[1] - tr[1]) if (est is not None and tr is not None) else float("nan")
        rows.append([k, round(t, 4), mode, int(ch is not None),
                     round(z[0], 3) if z is not None else "", round(z[1], 3) if z is not None else "",
                     round(est[0], 3) if est is not None else "", round(est[1], 3) if est is not None else "",
                     round(ch.snr, 2) if ch is not None else "", round(ch.score, 3) if ch is not None else "",
                     tr[0] if tr else "", tr[1] if tr else "", round(ce, 4) if not math.isnan(ce) else "",
                     round(ee, 4) if not math.isnan(ee) else "", round(ms, 3)])
        k += 1
    wall = time.perf_counter() - wall0
    cols = ["frame", "t", "mode", "detected", "meas_x", "meas_y", "est_x", "est_y", "snr", "confidence",
            "truth_x", "truth_y", "centroid_err_px", "est_err_px", "proc_ms"]
    with open(out / "video_frames.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    ce = np.array([r[12] for r in rows if r[12] != ""], float)
    ee = np.array([r[13] for r in rows if r[13] != ""], float)
    proc = np.array([r[14] for r in rows], float)
    det = np.array([r[3] for r in rows], int)
    tracked = np.array([r[2] in ("TRACK",) for r in rows])
    first = int(np.argmax(tracked)) if tracked.any() else -1
    # re-acquisition after truth-visible gaps (loss episodes)
    s = {
        "video": str(path), "frames": k, "resolution": [W, H], "fps_video": fps,
        "processing_ms_mean": float(proc.mean()) if k else float("nan"),
        "processing_ms_p95": float(np.percentile(proc, 95)) if k else float("nan"),
        "fps_processing": 1000.0 / float(proc.mean()) if k else float("nan"),
        "fps_end_to_end_incl_decode": k / wall if wall > 0 else float("nan"),
        "acquisition_time_s": first / fps if first >= 0 else float("nan"),
        "detection_rate_pct": 100.0 * det.mean() if k else 0.0,
        "lock_retention_pct": 100.0 * tracked[first:].mean() if first >= 0 else 0.0,
        "centroid_error_px": {"mean": float(ce.mean()) if len(ce) else float("nan"),
                              "rmse": float(np.sqrt((ce ** 2).mean())) if len(ce) else float("nan"),
                              "max": float(ce.max()) if len(ce) else float("nan"),
                              "p95": float(np.percentile(ce, 95)) if len(ce) else float("nan"), "n": int(len(ce))},
        "estimate_error_px": {"mean": float(ee.mean()) if len(ee) else float("nan"),
                              "rmse": float(np.sqrt((ee ** 2).mean())) if len(ee) else float("nan")},
        "truth_available": bool(truth),
        "note": "centroid_err uses the RAW per-frame measurement; est_err uses the IMM-filtered estimate",
    }
    (out / "video_summary.json").write_text(json.dumps(s, indent=1))
    return s
