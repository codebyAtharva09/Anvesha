"""Aggregate benchmark report: tables + comparison charts across pipelines."""
from __future__ import annotations

import html
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .report import GRID, INK, MUTED, _png, _style  # noqa: E402

PIPE_COL = {"baseline_a": "#9aa5b1", "baseline_b": "#6c7a89", "baseline_c": "#d9822b", "anvesha": "#1f6fb2",
            "abl_no_belief": "#b8c4d0", "abl_no_zoom": "#8fb3d9", "abl_no_imu_ff": "#5e9bd1", "abl_no_jitter_R": "#c9a227",
            "abl_no_cnn": "#2e8b57", "abl_kf_cv": "#8e6c8a"}
LABEL = {"baseline_a": "A: threshold+PID", "baseline_b": "B: blob+KF+PID", "baseline_c": "C: CNN+KF+PID", "anvesha": "ANVESHA"}

METRICS = [("acq_time_mean_s", "Acquisition time (s, mean)", 2.0),
           ("err_los_mean_px", "LOS tracking error (px, mean)", 10.0),
           ("err_img_mean_px", "Image-plane error incl. jitter (px, mean)", 10.0),
           ("loss_pct_excl_occ", "Target loss (% frames, excl. occlusion)", 5.0),
           ("reacq_max_s", "Re-acquisition time (s, max)", 1.0),
           ("centroid_err_rms_px", "Centroiding error (px RMS)", None),
           ("fps_loop", "Loop FPS", 20.0)]


def _v(x):
    return float("nan") if x is None else float(x)


def bench_report(out_dir: str) -> Path:
    out = Path(out_dir)
    agg = json.loads((out / "summary.json").read_text())
    scen = sorted({v["scenario"] for v in agg.values()})
    pipes = [p for p in PIPE_COL if any(v["pipeline"] == p for v in agg.values())]
    imgs = []
    for key, title, lim in METRICS:
        fig, ax = plt.subplots(figsize=(10, 2.8))
        w = 0.8 / max(len(pipes), 1)
        for i, p in enumerate(pipes):
            vals = [_v(agg.get(f"{s}|{p}", {}).get(key)) for s in scen]
            vals_plot = [0 if math.isnan(v) else v for v in vals]
            bars = ax.bar(np.arange(len(scen)) + i * w - 0.4 + w / 2, vals_plot, w, color=PIPE_COL[p], label=LABEL.get(p, p))
            for b, v in zip(bars, vals):
                if math.isnan(v):
                    ax.text(b.get_x() + b.get_width() / 2, 0, "×", ha="center", va="bottom", fontsize=7, color="#c0392b")
        if lim:
            ax.axhline(lim, color="#c0392b", ls="--", lw=0.9)
        ax.set_xticks(range(len(scen)))
        ax.set_xticklabels(scen, rotation=30, ha="right", fontsize=7)
        if key in ("err_los_mean_px", "err_img_mean_px", "acq_time_mean_s", "reacq_max_s"):
            ax.set_yscale("symlog", linthresh=1)
        ax.legend(fontsize=7, frameon=False, ncol=len(pipes))
        _style(ax, title + ("   (dashed = PS limit; × = not achieved)" if lim else ""))
        imgs.append(_png(fig))
        plt.close(fig)
    head = "".join(f"<th>{html.escape(t)}</th>" for t in ["Scenario", "Pipeline", "Acq %", "Acq mean s", "Acq max s", "LOS err px", "Img err px", "Centroid RMS px",
                                                           "Loss %", "Reacq max s", "Unrecov.", "False-lock fr", "FPS"])
    body = ""
    for s in scen:
        for p in pipes:
            r = agg.get(f"{s}|{p}")
            if not r:
                continue
            f = lambda k, nd=2: "—" if (r.get(k) is None or (isinstance(r.get(k), float) and math.isnan(r.get(k)))) else f"{r[k]:.{nd}f}"
            body += (f"<tr class='{p}'><td>{s}</td><td>{LABEL.get(p, p)}</td><td>{f('acquired_pct', 0)}</td><td>{f('acq_time_mean_s')}</td><td>{f('acq_time_max_s')}</td>"
                     f"<td>{f('err_los_mean_px')}</td><td>{f('err_img_mean_px')}</td><td>{f('centroid_err_rms_px', 3)}</td><td>{f('loss_pct_excl_occ')}</td>"
                     f"<td>{f('reacq_max_s')}</td><td>{r.get('reacq_unrecovered', 0)}</td><td>{f('false_lock_frames', 1)}</td><td>{f('fps_loop', 0)}</td></tr>")
    doc = f"""<!doctype html><html><head><meta charset='utf-8'><title>ANVESHA benchmark</title><style>
body{{font:13px/1.45 'Segoe UI',system-ui,sans-serif;color:{INK};max-width:1200px;margin:24px auto;padding:0 16px}}
table{{border-collapse:collapse;width:100%;font-size:12px}} th,td{{border-bottom:1px solid {GRID};padding:3px 6px;text-align:right;font-variant-numeric:tabular-nums}}
th:nth-child(-n+2),td:nth-child(-n+2){{text-align:left}} tr.anvesha td{{background:#eef5fb;font-weight:600}} img{{max-width:100%}} .n{{color:{MUTED}}}</style></head><body>
<h1>ANVESHA — benchmark report</h1><p class='n'>Measured in simulation (software-in-the-loop). Means over seeds; all quantities from ground truth. Seeds and configs in runs.jsonl.</p>
{''.join(f"<img src='{u}'/>" for u in imgs)}<h2>Table</h2><table><tr>{head}</tr>{body}</table></body></html>"""
    p = out / "benchmark_report.html"
    p.write_text(doc, encoding="utf-8")
    return p
