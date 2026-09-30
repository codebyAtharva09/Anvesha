"""ANVESHA command-line interface.

  python -m anvesha gui                      # mission-control GUI (opens browser)
  python -m anvesha run  --scenario A_clean --pipeline anvesha --seed 1 --out results/runs/demo
  python -m anvesha bench --scenarios all --pipelines baseline_a baseline_b baseline_c anvesha --seeds 1 2 3
  python -m anvesha ablate --scenarios all --seeds 1 2 3
  python -m anvesha make-video --scenario M_combined --seconds 20 --out results/videos/M.mp4
  python -m anvesha video --input results/videos/M.mp4 --truth results/videos/M.truth.csv --out results/video_M
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config as C


def _scen_list(arg):
    from .bench.runner import SCEN_DIR
    if arg == ["all"] or arg == "all":
        return sorted(p.stem for p in SCEN_DIR.glob("*.yaml"))
    return arg


def main(argv=None):
    ap = argparse.ArgumentParser(prog="anvesha", description="Belief-driven coarse PAT simulator (SIH26169)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gui")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--no-browser", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="A_clean")
    r.add_argument("--pipeline", default="anvesha")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--duration", type=float)
    r.add_argument("--out", default="results/runs/latest")
    r.add_argument("--set", nargs="*", default=[], help="dotted overrides, e.g. noise.jitter_px=10")
    b = sub.add_parser("bench")
    b.add_argument("--scenarios", nargs="*", default=["all"])
    b.add_argument("--pipelines", nargs="*", default=["baseline_a", "baseline_b", "baseline_c", "anvesha"])
    b.add_argument("--seeds", nargs="*", type=int, default=[1, 2, 3])
    b.add_argument("--duration", type=float)
    b.add_argument("--workers", type=int)
    b.add_argument("--out", default="results/bench")
    b.add_argument("--save-runs", action="store_true")
    ab = sub.add_parser("ablate")
    ab.add_argument("--scenarios", nargs="*", default=["all"])
    ab.add_argument("--seeds", nargs="*", type=int, default=[1, 2, 3])
    ab.add_argument("--duration", type=float)
    ab.add_argument("--workers", type=int)
    ab.add_argument("--out", default="results/ablation")
    mv = sub.add_parser("make-video")
    mv.add_argument("--scenario")
    mv.add_argument("--seconds", type=float, default=20)
    mv.add_argument("--out", required=True)
    mv.add_argument("--seed", type=int)
    v = sub.add_parser("video")
    v.add_argument("--input", required=True)
    v.add_argument("--truth")
    v.add_argument("--out", default="results/video")
    v.add_argument("--beacon-size", type=float, default=10.0)
    v.add_argument("--detector", default="fusion")
    a = ap.parse_args(argv)

    if a.cmd == "gui":
        from .server.app import serve
        serve(a.port, open_browser=not a.no_browser)
    elif a.cmd == "run":
        from .bench.runner import build_cfg
        from .metrics.logger import write_run
        from .pat.engine import Engine
        cfg = build_cfg(a.scenario, a.pipeline, a.seed, a.duration)
        for kv in a.set:
            k, val = kv.split("=", 1)
            C.set_dotted(cfg, k, val)
        C.validate(cfg)
        eng = Engine(cfg)
        s = eng.run()
        p = write_run(Path(a.out), cfg, eng, s)
        print(json.dumps({k: s[k] for k in ("acquisition_time_s", "target_loss_pct", "fps_loop")}, default=float))
        print("report:", p / "report.html")
    elif a.cmd in ("bench", "ablate"):
        from .bench.runner import ABLATIONS, run_matrix
        from .report.bench_report import bench_report
        pipes = a.pipelines if a.cmd == "bench" else list(ABLATIONS.keys())
        res = run_matrix(_scen_list(a.scenarios), pipes, a.seeds, a.duration, a.out, a.workers,
                         getattr(a, "save_runs", False))
        print("report:", bench_report(a.out))
    elif a.cmd == "make-video":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        from make_benchmark_video import make
        from .bench.runner import SCEN_DIR
        scen = None
        if a.scenario:
            scen = a.scenario if a.scenario.endswith(".yaml") else str(SCEN_DIR / f"{a.scenario}.yaml")
        print(make(scen, a.seconds, a.out, seed=a.seed))
    elif a.cmd == "video":
        from .video.runner import run_video
        s = run_video(a.input, a.out, a.truth, a.beacon_size, a.detector)
        print(json.dumps(s, indent=1, default=float))


if __name__ == "__main__":
    main()
