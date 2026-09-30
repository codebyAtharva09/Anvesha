"""Benchmark engine: scenarios x pipelines x seeds (+ ablations), in parallel.

Every run is fully determined by (scenario file, pipeline, seed); the exact
configuration is stored next to its results. Results are *measured* from the
simulation ground truth - nothing is typed in by hand.
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .. import config as C
from ..pat.engine import Engine

ROOT = Path(__file__).resolve().parents[2]
SCEN_DIR = ROOT / "configs" / "scenarios"

ABLATIONS: Dict[str, Dict] = {
    "anvesha": {},
    "abl_no_belief": {"search": {"kind": "spiral", "allow_zoom": False}},
    "abl_no_zoom": {"search": {"allow_zoom": False}},
    "abl_no_imu_ff": {"control": {"imu_feedforward": False}},
    "abl_no_jitter_R": {"estimator": {"adaptive_r": False}},
    "abl_no_cnn": {"perception": {"detector": "mf_cfar", "use_cnn_verifier": False}},
    "abl_kf_cv": {"estimator": {"kind": "kf_cv"}},
}


def build_cfg(scenario: str, pipeline: str, seed: int, duration: Optional[float] = None,
              overrides: Optional[Dict] = None) -> C.Config:
    cfg = C.load(SCEN_DIR / f"{scenario}.yaml") if not scenario.endswith(".yaml") else C.load(scenario)
    base_pipe = "anvesha" if pipeline.startswith("abl_") else pipeline
    cfg = C.apply_pipeline(cfg, base_pipe)
    if pipeline in ABLATIONS and ABLATIONS[pipeline]:
        cfg = C.from_dict(ABLATIONS[pipeline], cfg)
    if overrides:
        cfg = C.from_dict(overrides, cfg)
    cfg.run.seed = seed
    if duration:
        cfg.run.duration_s = duration
    return cfg


def _one(args) -> Dict:
    scenario, pipeline, seed, duration, save_dir, overrides = args
    cfg = build_cfg(scenario, pipeline, seed, duration, overrides)
    t0 = time.perf_counter()
    eng = Engine(cfg)
    s = eng.run()
    s["wall_s"] = time.perf_counter() - t0
    s["scenario"], s["pipeline"], s["seed"] = scenario, pipeline, seed
    if save_dir:
        d = Path(save_dir) / scenario / pipeline
        d.mkdir(parents=True, exist_ok=True)
        from ..metrics.logger import write_run
        write_run(d / f"seed{seed}", cfg, eng, s)
    return s


def run_matrix(scenarios: List[str], pipelines: List[str], seeds: List[int], duration: Optional[float] = None,
               out_dir: str = "results/bench", workers: Optional[int] = None, save_runs: bool = False,
               overrides: Optional[Dict] = None, progress=True) -> List[Dict]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(s, p, k, duration, str(out / "runs") if save_runs else None, overrides)
            for s in scenarios for p in pipelines for k in seeds]
    workers = workers or max(1, min(os.cpu_count() or 1, 4))
    res: List[Dict] = []
    t0 = time.time()
    if workers > 1:
        with mp.get_context("spawn").Pool(workers) as pool:
            for i, r in enumerate(pool.imap_unordered(_one, jobs)):
                res.append(r)
                if progress and (i % 10 == 0 or i == len(jobs) - 1):
                    print(f"[{i + 1}/{len(jobs)}] {time.time() - t0:.0f}s  {r['scenario']} {r['pipeline']} s{r['seed']}", flush=True)
    else:
        for i, j in enumerate(jobs):
            res.append(_one(j))
    with open(out / "runs.jsonl", "w") as f:
        for r in res:
            f.write(json.dumps(r, default=float) + "\n")
    agg = aggregate(res)
    (out / "summary.json").write_text(json.dumps(agg, indent=1, default=float))
    return res


def _nan(x):
    return float("nan") if x is None else x


def aggregate(res: List[Dict]) -> Dict:
    """Mean / worst over seeds for each (scenario, pipeline)."""
    groups: Dict[Tuple[str, str], List[Dict]] = {}
    for r in res:
        groups.setdefault((r["scenario"], r["pipeline"]), []).append(r)
    out = {}
    for (sc, pl), rs in sorted(groups.items()):
        acq = np.array([r["acquisition_time_s"] for r in rs], float)
        acq_ok = np.array([r["acquired"] for r in rs], bool)
        def m(key, sub=None):
            v = np.array([(r[key][sub] if sub else r[key]) for r in rs], float)
            return float(np.nanmean(v)) if np.isfinite(v).any() else float("nan")
        reacq_all = [x for r in rs for x in r["reacquisition_times_s"]]
        reacq_f = [x for x in reacq_all if not (isinstance(x, float) and math.isnan(x))]
        out[f"{sc}|{pl}"] = {
            "scenario": sc, "pipeline": pl, "n_seeds": len(rs),
            "acquired_pct": 100.0 * acq_ok.mean(),
            "acq_time_mean_s": float(np.nanmean(acq)) if np.isfinite(acq).any() else float("nan"),
            "acq_time_max_s": float(np.nanmax(acq)) if np.isfinite(acq).any() else float("nan"),
            "acq_le_2s_pct": 100.0 * float(np.mean([(a <= 2.0) for a in acq])),
            "err_img_mean_px": m("tracking_error_img_px", "mean"),
            "err_img_rms_px": m("tracking_error_img_px", "rms"),
            "err_img_max_px": float(np.nanmax([r["tracking_error_img_px"]["max"] for r in rs])) if any(np.isfinite([r["tracking_error_img_px"]["max"] for r in rs])) else float("nan"),
            "err_los_mean_px": m("tracking_error_los_px", "mean"),
            "err_los_rms_px": m("tracking_error_los_px", "rms"),
            "centroid_err_mean_px": m("centroid_error_px", "mean"),
            "centroid_err_rms_px": m("centroid_error_px", "rms"),
            "loss_pct": m("target_loss_pct"),
            "loss_pct_excl_occ": m("target_loss_pct_excl_occlusion"),
            "lock_retention_pct": m("lock_retention_pct"),
            "reacq_events": len(reacq_all),
            "reacq_unrecovered": len(reacq_all) - len(reacq_f),
            "reacq_mean_s": float(np.mean(reacq_f)) if reacq_f else float("nan"),
            "reacq_max_s": float(np.max(reacq_f)) if reacq_f else float("nan"),
            "false_lock_frames": m("false_lock_frames"),
            "proc_ms_mean": m("processing_ms", "mean"),
            "proc_ms_p95": m("processing_ms", "p95"),
            "fps_loop": m("fps_loop"),
            "fps_processing": m("fps_processing"),
            "settling_s": m("settling_time_s"),
            "rate_sat_pct": m("rate_saturation_pct"),
        }
    return out
