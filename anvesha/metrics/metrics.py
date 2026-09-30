"""Ground-truth metrics engine.

Definitions (all distances in *base-FOV pixels* = screen px; 1 px = deg_per_px):

pointing error e_img   |target - true LOS incl. jitter|  (what the camera sees:
                       beacon offset from the image centre, scaled by zoom)
pointing error e_los   |target - LOS from gimbal+platform| (jitter excluded; the
                       part a coarse gimbal can actually correct)
centroiding error      |measured centroid - true beacon centre| (camera px),
                       only for frames where the chosen detection is the beacon
on-target (locked)     mode in {TRACK, COAST} AND estimate within max(3*size,25)
                       px of truth AND beacon inside FOV
acquisition time       first frame with mode TRACK and e_los <= lock_px (PS #16)
target loss (%)        after first acquisition: frames not on-target / frames
                       (reported with and without scripted occlusion windows)
lock retention (%)     100 - target loss
re-acquisition time    for each loss episode: time from loss start (or from
                       the end of a scripted occlusion) to the next on-target
false-lock frames      mode TRACK but estimate > 3*size+25 px from the truth
processing time        perception+association+estimation+search per frame
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from ..config import Config

COLUMNS = ["t", "mode", "visible", "occluded", "zoom", "tgt_x", "tgt_y", "tgt_vx", "tgt_vy", "los_x", "los_y",
           "jit_x", "jit_y", "pan_deg", "tilt_deg", "pan_rate_dps", "tilt_rate_dps", "plat_x", "plat_y",
           "beacon_u", "beacon_v", "meas_u", "meas_v", "est_x", "est_y", "err_img_px", "err_los_px",
           "centroid_err_px", "est_err_px", "on_target", "false_lock", "confidence", "snr", "n_det",
           "proc_ms", "render_ms", "noise_sigma", "sp_frac", "pd", "nis", "sat"]


class MetricsEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.dpp = cfg.deg_per_px
        self.rows: List[list] = []
        self.center = np.array([cfg.screen.width_px / 2.0, cfg.screen.height_px / 2.0])
        self.size = cfg.target.size_px
        self.lock_px = cfg.run.lock_px

    def add(self, tr, rep, render_ms: float) -> None:
        tgt = tr.target_xy
        los = tr.boresight_xy
        los0 = tr.los_nojitter_xy
        # gimbal-frame truth of the target (what the estimator estimates)
        tgt_g = tgt - tr.platform_px
        e_img = float(np.linalg.norm(tgt - los))
        e_los = float(np.linalg.norm(tgt - los0))
        est_err = float("nan")
        if rep.est_g is not None:
            est_err = float(np.linalg.norm(rep.est_g - (tgt_g)))
        c_err = float("nan")
        mu = mv = float("nan")
        if rep.chosen is not None:
            mu, mv = rep.chosen.u, rep.chosen.v
            if tr.visible:
                d = math.hypot(mu - tr.beacon_uv[0], mv - tr.beacon_uv[1])
                if d * tr.zoom < 3 * self.size + 10:
                    c_err = d
        tol = max(3 * self.size, 25.0)
        in_fov = e_img < 0.5 * min(self.cfg.camera.width_px, self.cfg.camera.height_px) * tr.zoom
        tracking = rep.mode in ("TRACK", "COAST")
        on_target = bool(tracking and not math.isnan(est_err) and est_err <= tol and in_fov)
        false_lock = bool(rep.mode == "TRACK" and not math.isnan(est_err) and est_err > tol + self.size)
        self.rows.append([
            tr.t, rep.mode, int(tr.visible), int(tr.occluded), tr.zoom, tgt[0], tgt[1], tr.target_vel[0],
            tr.target_vel[1], los[0], los[1], tr.jitter_px[0], tr.jitter_px[1], tr.gimbal_px[0] * self.dpp,
            tr.gimbal_px[1] * self.dpp, tr.gimbal_rate_px[0] * self.dpp, tr.gimbal_rate_px[1] * self.dpp,
            tr.platform_px[0], tr.platform_px[1], tr.beacon_uv[0], tr.beacon_uv[1], mu, mv,
            rep.est_g[0] if rep.est_g is not None else float("nan"), rep.est_g[1] if rep.est_g is not None else float("nan"),
            e_img, e_los, c_err, est_err, int(on_target), int(false_lock), rep.confidence,
            rep.chosen.snr if rep.chosen is not None else float("nan"), len(rep.detections), rep.proc_ms, render_ms,
            rep.stats.pix_sigma, rep.stats.sp_frac, rep.pd, rep.nis, int(any(tr.extra.get("saturated", [False])))])

    # ------------------------------------------------------------------ #
    def arrays(self) -> Dict[str, np.ndarray]:
        if not self.rows:
            return {}
        cols = list(zip(*self.rows))
        out = {}
        for name, col in zip(COLUMNS, cols):
            out[name] = np.array(col) if name == "mode" else np.array(col, dtype=float)
        return out

    def summary(self) -> Dict:
        A = self.arrays()
        if not A:
            return {}
        t = A["t"]
        n = len(t)
        mode = A["mode"]
        on = A["on_target"].astype(bool)
        occ = A["occluded"].astype(bool)
        e_img, e_los = A["err_img_px"], A["err_los_px"]
        dt = float(np.median(np.diff(t))) if n > 1 else 1 / 30
        acq_idx = np.nonzero((mode == "TRACK") & (e_los <= self.lock_px) & on)[0]
        acquired = len(acq_idx) > 0
        i0 = int(acq_idx[0]) if acquired else n
        acq_time = float(t[i0] - t[0]) if acquired else float("nan")
        post = np.arange(i0, n)
        loss_frames = int((~on[post]).sum()) if acquired else n
        post_n = max(len(post), 1)
        post_noocc = post[~occ[post]] if acquired else post
        # a short grace window after scripted occlusions is part of re-acquisition, not "loss"
        loss_pct = 100.0 * loss_frames / post_n if acquired else 100.0
        loss_pct_ex_occ = 100.0 * float((~on[post_noocc]).sum()) / max(len(post_noocc), 1) if acquired else 100.0
        # loss episodes and re-acquisition times
        reacq = []
        if acquired:
            i = i0
            while i < n:
                if not on[i]:
                    j = i
                    while j < n and not on[j]:
                        j += 1
                    start_t = t[i]
                    # if the loss was caused by a scripted occlusion, time from its end
                    if occ[i:j].any():
                        occ_end = i + int(np.nonzero(occ[i:j])[0][-1]) + 1
                        start_t = t[min(occ_end, n - 1)]
                    if j < n:
                        reacq.append(float(max(t[j] - start_t, 0.0)))
                    else:
                        reacq.append(float("nan"))  # never recovered within the run
                    i = j
                else:
                    i += 1
        lk = post[on[post]] if acquired else np.array([], int)
        def stats(x):
            x = x[~np.isnan(x)]
            if len(x) == 0:
                return {"mean": float("nan"), "rms": float("nan"), "max": float("nan"), "p95": float("nan")}
            return {"mean": float(np.mean(x)), "rms": float(np.sqrt(np.mean(x ** 2))), "max": float(np.max(x)),
                    "p95": float(np.percentile(x, 95))}
        ce = A["centroid_err_px"]
        proc = A["proc_ms"]
        rend = A["render_ms"]
        fps_proc = 1000.0 / max(float(np.mean(proc)), 1e-6)
        loop = proc + rend
        fps_loop = 1000.0 / max(float(np.mean(loop)), 1e-6)
        # control quality after acquisition: settling time to stay within lock_px for 1 s
        settle = float("nan")
        if acquired:
            win = int(round(1.0 / dt))
            ok = e_los <= self.lock_px
            for k in range(i0, n - win):
                if ok[k:k + win].all():
                    settle = float(t[k] - t[i0])
                    break
        rates = np.stack([A["pan_rate_dps"], A["tilt_rate_dps"]], 1)
        s = {
            "frames": n,
            "duration_s": float(t[-1] - t[0] + dt),
            "acquired": bool(acquired),
            "acquisition_time_s": acq_time,
            "tracking_error_img_px": stats(e_img[lk]) if acquired else stats(np.array([np.nan])),
            "tracking_error_los_px": stats(e_los[lk]) if acquired else stats(np.array([np.nan])),
            "centroid_error_px": stats(ce),
            "target_loss_pct": loss_pct,
            "target_loss_pct_excl_occlusion": loss_pct_ex_occ,
            "lock_retention_pct": 100.0 - loss_pct,
            "reacquisition_times_s": reacq,
            "reacquisition_time_max_s": float(np.nanmax(reacq)) if reacq and not all(math.isnan(r) for r in reacq) else float("nan"),
            "reacquisition_time_mean_s": float(np.nanmean(reacq)) if reacq and not all(math.isnan(r) for r in reacq) else float("nan"),
            "unrecovered_losses": int(sum(1 for r in reacq if math.isnan(r))),
            "loss_events": len(reacq),
            "false_lock_frames": int(A["false_lock"].sum()),
            "processing_ms": {"mean": float(np.mean(proc)), "p95": float(np.percentile(proc, 95)), "max": float(np.max(proc))},
            "render_ms_mean": float(np.mean(rend)),
            "fps_processing": fps_proc,
            "fps_processing_min": 1000.0 / max(float(np.percentile(proc, 99)), 1e-6),
            "fps_loop": fps_loop,
            "settling_time_s": settle,
            "rate_saturation_pct": 100.0 * float(A["sat"].mean()),
            "rate_rms_dps": float(np.sqrt(np.mean(np.sum(rates ** 2, 1)))),
            "mean_confidence_tracking": float(np.mean(A["confidence"][lk])) if len(lk) else float("nan"),
        }
        # PS26169 pass/fail flags (reported, not asserted)
        s["ps_checks"] = {
            "acquisition_le_2s": bool(acquired and acq_time <= 2.0),
            "tracking_error_le_10px_img": bool(acquired and s["tracking_error_img_px"]["mean"] <= 10.0),
            "tracking_error_le_10px_los": bool(acquired and s["tracking_error_los_px"]["mean"] <= 10.0),
            "target_loss_lt_5pct": bool(loss_pct_ex_occ < 5.0),
            "reacquisition_le_1s": bool(len(reacq) == 0 or (not math.isnan(s["reacquisition_time_max_s"]) and s["reacquisition_time_max_s"] <= 1.0 and s["unrecovered_losses"] == 0)),
            "fps_ge_20": bool(fps_loop >= 20.0),
        }
        return s
