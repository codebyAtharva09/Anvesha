"""Generate Benchmark-2-style test videos: full-screen (default 2000x2000),
30 fps .mp4 with a moving beacon and the selected disturbances, plus a truth
CSV (frame, t, x, y, visible). Used to rehearse the evaluator's video test.

Example:
  python tools/make_benchmark_video.py --scenario configs/scenarios/M_combined.yaml --seconds 20 \
         --out results/videos/M_combined.mp4
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anvesha import config as C  # noqa: E402
from anvesha.sim.world import SimWorld  # noqa: E402


def make(scenario: str | None, seconds: float, out: str, size: int = 2000, seed: int | None = None,
         overrides=()) -> str:
    cfg = C.load(scenario) if scenario else C.Config()
    for kv in overrides:
        k, v = kv.split("=", 1)
        C.set_dotted(cfg, k, v)
    if seed is not None:
        cfg.run.seed = seed
    # the "camera" is the whole screen: same angular scale as the 4 deg / 640 px default
    dpp = cfg.deg_per_px
    cfg.screen.width_px = cfg.screen.height_px = size
    cfg.camera.width_px = cfg.camera.height_px = size
    cfg.camera.fov_x_deg = cfg.camera.fov_y_deg = dpp * size
    cfg.camera.zoom_levels = [1.0]
    cfg.target.initial = "random"
    w = SimWorld(cfg)
    fps = cfg.camera.rate_hz
    outp = Path(out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(outp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (size, size), False)
    steps = int(round(cfg.run.sim_rate_hz / fps))
    with open(outp.with_suffix(".truth.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["frame", "t", "x", "y", "visible"])
        for k in range(int(seconds * fps)):
            fr, tr = w.capture()
            vw.write(fr)
            wr.writerow([k, round(tr.t, 4), round(float(tr.beacon_uv[0]), 4), round(float(tr.beacon_uv[1]), 4),
                         int(tr.visible)])
            for _ in range(steps):
                w.step()
    vw.release()
    return str(outp)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=2000)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--set", nargs="*", default=[])
    a = ap.parse_args()
    print(make(a.scenario, a.seconds, a.out, a.size, a.seed, a.set))
