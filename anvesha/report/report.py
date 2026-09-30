"""Automatic performance report generator (PS deliverable: performance log).

Produces, for every run:
  report.html  self-contained (charts embedded as PNG data URIs)
  report.pdf   charts + summary table (matplotlib PdfPages)
Content: experiment ID, date/time, scenario, trajectory, FOV, noise,
atmosphere, platform motion, jitter, FPS (mean/min), tracking error
(mean/RMS/max, image-plane and LOS), centroiding error, acquisition time,
re-acquisition times, target loss, lock retention, processing latency,
controller statistics, PS pass/fail table and the event log.
"""
from __future__ import annotations

import base64
import html
import io
import math
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

INK, MUTED, GRID = "#1d2733", "#5b6776", "#dde3ea"
C1, C2, C3, RED = "#1f6fb2", "#d9822b", "#2e8b57", "#c0392b"
MODE_COL = {"SEARCH": "#9aa5b1", "ACQUIRE": "#d9822b", "TRACK": "#2e8b57", "COAST": "#c9a227", "REACQUIRE": "#c0392b"}


def _style(ax, title, xl=None, yl=None):
    ax.set_title(title, fontsize=10, color=INK, loc="left", fontweight="bold")
    if xl:
        ax.set_xlabel(xl, fontsize=8, color=MUTED)
    if yl:
        ax.set_ylabel(yl, fontsize=8, color=MUTED)
    ax.tick_params(labelsize=7, colors=MUTED)
    ax.grid(True, color=GRID, lw=0.6)
    for s in ax.spines.values():
        s.set_color(GRID)


def _png(fig) -> str:
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=110, bbox_inches="tight")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def figures(A: Dict[str, np.ndarray], cfg) -> List:
    t = A["t"]
    figs = []
    lock = cfg.run.lock_px
    # 1 pointing error
    fig, ax = plt.subplots(figsize=(8, 2.6))
    ax.plot(t, A["err_img_px"], color=C2, lw=0.8, label="image-plane error (incl. jitter)")
    ax.plot(t, A["err_los_px"], color=C1, lw=1.1, label="LOS error (correctable)")
    ax.axhline(lock, color=RED, ls="--", lw=0.9, label=f"PS limit {lock:g} px")
    ax.set_ylim(0, max(4 * lock, np.nanpercentile(np.r_[A["err_los_px"], [lock]], 90) * 1.3))
    ax.legend(fontsize=7, frameon=False, ncol=3)
    _style(ax, "Pointing error vs time", "time (s)", "px")
    figs.append(("Pointing error", fig))
    # 2 mode timeline + confidence
    fig, ax = plt.subplots(figsize=(8, 1.9))
    modes = A["mode"]
    for i in range(len(t) - 1):
        ax.axvspan(t[i], t[i + 1], ymin=0.0, ymax=0.25, color=MODE_COL.get(modes[i], "#999"), lw=0)
    ax.plot(t, A["confidence"], color=INK, lw=0.9, label="track confidence")
    ax.set_ylim(-0.02, 1.02)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in MODE_COL.values()]
    ax.legend(handles, list(MODE_COL.keys()), fontsize=6, frameon=False, ncol=5, loc="upper right")
    _style(ax, "PAT mode timeline and confidence", "time (s)", "")
    figs.append(("Mode", fig))
    # 3 screen trajectory
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.plot(A["tgt_x"], A["tgt_y"], color=C2, lw=1.0, label="beacon (truth)")
    ax.plot(A["los_x"], A["los_y"], color=C1, lw=0.7, alpha=0.8, label="camera boresight")
    ax.set_xlim(0, cfg.screen.width_px)
    ax.set_ylim(cfg.screen.height_px, 0)
    ax.set_aspect("equal")
    ax.legend(fontsize=7, frameon=False)
    _style(ax, "Virtual screen: beacon vs boresight", "x (px)", "y (px)")
    figs.append(("Trajectory", fig))
    # 4 rates
    fig, ax = plt.subplots(figsize=(8, 2.2))
    ax.plot(t, A["pan_rate_dps"], color=C1, lw=0.9, label="pan rate")
    ax.plot(t, A["tilt_rate_dps"], color=C3, lw=0.9, label="tilt rate")
    for s in (1, -1):
        ax.axhline(s * cfg.gimbal.max_pan_rate_dps, color=RED, ls="--", lw=0.8)
    ax.legend(fontsize=7, frameon=False, ncol=2)
    _style(ax, "Gimbal rates (limit dashed)", "time (s)", "deg/s")
    figs.append(("Rates", fig))
    # 5 processing
    fig, ax = plt.subplots(figsize=(8, 2.0))
    ax.plot(t, A["proc_ms"], color=C1, lw=0.7, label="tracking pipeline (ms)")
    ax.plot(t, A["proc_ms"] + A["render_ms"], color=MUTED, lw=0.6, alpha=0.7, label="+ scene rendering (ms)")
    ax.axhline(50, color=RED, ls="--", lw=0.8, label="20 FPS budget")
    ax.legend(fontsize=7, frameon=False, ncol=3)
    _style(ax, "Per-frame processing time", "time (s)", "ms")
    figs.append(("Processing", fig))
    # 6 centroid error histogram
    ce = A["centroid_err_px"]
    ce = ce[np.isfinite(ce)]
    fig, ax = plt.subplots(figsize=(4, 2.6))
    if len(ce):
        ax.hist(ce, bins=40, color=C1, alpha=0.85)
    _style(ax, "Centroiding error distribution", "px (camera)", "frames")
    figs.append(("Centroid", fig))
    return figs


def _fmt(x, nd=2):
    if x is None:
        return "—"
    try:
        if isinstance(x, float) and math.isnan(x):
            return "—"
        return f"{x:.{nd}f}"
    except Exception:
        return str(x)


def run_report(base: Path, cfg, A: Dict[str, np.ndarray], s: Dict, events: List[str]) -> Path:
    base = Path(base)
    figs = figures(A, cfg) if A else []
    imgs = [(n, _png(f)) for n, f in figs]
    with PdfPages(base / "report.pdf") as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.06, 0.95, "ANVESHA performance report", fontsize=16, color=INK, fontweight="bold")
        fig.text(0.06, 0.925, s.get("experiment_id", ""), fontsize=8, color=MUTED)
        lines = _kv(cfg, s)
        y = 0.89
        for k, v in lines:
            fig.text(0.06, y, k, fontsize=8, color=MUTED)
            fig.text(0.42, y, v, fontsize=8, color=INK)
            y -= 0.018
        pdf.savefig(fig)
        plt.close(fig)
        for _, f in figs:
            pdf.savefig(f)
            plt.close(f)
    ps = s.get("ps_checks", {})
    rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>" for k, v in _kv(cfg, s))
    checks = "".join(
        f"<tr><td>{html.escape(k)}</td><td class='{'ok' if v else 'bad'}'>{'PASS' if v else 'NOT MET'}</td></tr>"
        for k, v in ps.items())
    im = "".join(f"<figure><img src='{u}' alt='{html.escape(n)}'/></figure>" for n, u in imgs)
    ev = html.escape("\n".join(events[-200:]))
    doc = f"""<!doctype html><html><head><meta charset='utf-8'><title>ANVESHA report {html.escape(s.get('experiment_id', ''))}</title>
<style>body{{font:13px/1.45 'Segoe UI',system-ui,sans-serif;color:{INK};max-width:980px;margin:24px auto;padding:0 16px;background:#fff}}
h1{{font-size:20px;margin:0}} .sub{{color:{MUTED};font-size:12px;margin-bottom:14px}}
table{{border-collapse:collapse;width:100%;margin:10px 0 18px}} td{{border-bottom:1px solid {GRID};padding:4px 8px;font-variant-numeric:tabular-nums}}
td:first-child{{color:{MUTED};width:42%}} .ok{{color:#1e7b45;font-weight:600}} .bad{{color:{RED};font-weight:600}}
figure{{margin:8px 0}} img{{max-width:100%}} pre{{background:#f5f7f9;padding:10px;font-size:11px;max-height:320px;overflow:auto}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} @media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
.note{{color:{MUTED};font-size:11px}}</style></head><body>
<h1>ANVESHA — automatic performance report</h1><div class='sub'>{html.escape(s.get('experiment_id', ''))} · generated {html.escape(s.get('created', ''))}</div>
<div class='grid'><div><h3>Run & results</h3><table>{rows}</table></div><div><h3>SIH26169 criteria</h3><table>{checks}</table>
<p class='note'>All values are computed from simulation ground truth by the metrics engine. Image-plane error includes camera jitter; LOS error excludes the white jitter component that a coarse gimbal cannot correct.</p></div></div>
{im}<h3>Event log</h3><pre>{ev}</pre></body></html>"""
    (base / "report.html").write_text(doc, encoding="utf-8")
    return base / "report.html"


def _kv(cfg, s):
    n, a, p = cfg.noise, cfg.atmosphere, cfg.platform
    noise = ", ".join(x for x in [f"Gaussian σ={n.gaussian_sigma:g}" if n.gaussian else "", f"Poisson ×{n.poisson_scale:g}" if n.poisson else "",
                                  f"S&P {100 * n.salt_pepper_frac:.0f}%" if n.salt_pepper else ""] if x) or "none"
    te_i, te_l, ce = s.get("tracking_error_img_px", {}), s.get("tracking_error_los_px", {}), s.get("centroid_error_px", {})
    rq = s.get("reacquisition_times_s", [])
    return [
        ("Scenario", f"{cfg.name} — {cfg.description[:70]}"),
        ("Pipeline / seed", f"{cfg.run.pipeline} / {cfg.run.seed}"),
        ("Simulation duration", f"{_fmt(s.get('duration_s'))} s ({s.get('frames', 0)} frames)"),
        ("Target trajectory / speed", f"{cfg.target.trajectory} / {cfg.target.speed_px_s:g} px/s, size {cfg.target.size_px:g} px"),
        ("Camera FOV / resolution / rate", f"{cfg.camera.fov_x_deg:g}°×{cfg.camera.fov_y_deg:g}° / {cfg.camera.width_px}×{cfg.camera.height_px} / {cfg.camera.rate_hz:g} Hz"),
        ("Pan/tilt rate limits", f"{cfg.gimbal.max_pan_rate_dps:g} / {cfg.gimbal.max_tilt_rate_dps:g} °/s; control {cfg.control.rate_hz:g} Hz"),
        ("Image noise", noise),
        ("Camera jitter", f"±{n.jitter_px:g} px/frame ({n.jitter_mode})"),
        ("Atmosphere", f"{a.condition} (severity {a.severity:g}), turbulence {a.turbulence:g}"),
        ("Platform motion", f"{p.motion} {p.amplitude_px_per_frame:g} px/frame"),
        ("FPS (loop mean / min 1%)", f"{_fmt(s.get('fps_loop'), 1)} / {_fmt(s.get('fps_processing_min'), 1)}"),
        ("Processing time mean / p95 / max", f"{_fmt(s.get('processing_ms', {}).get('mean'))} / {_fmt(s.get('processing_ms', {}).get('p95'))} / {_fmt(s.get('processing_ms', {}).get('max'))} ms"),
        ("Acquisition time", f"{_fmt(s.get('acquisition_time_s'))} s"),
        ("Tracking error, image (mean/RMS/max)", f"{_fmt(te_i.get('mean'))} / {_fmt(te_i.get('rms'))} / {_fmt(te_i.get('max'))} px"),
        ("Tracking error, LOS (mean/RMS/max)", f"{_fmt(te_l.get('mean'))} / {_fmt(te_l.get('rms'))} / {_fmt(te_l.get('max'))} px"),
        ("Centroiding error (mean/RMS/max)", f"{_fmt(ce.get('mean'), 3)} / {_fmt(ce.get('rms'), 3)} / {_fmt(ce.get('max'), 3)} px"),
        ("Target loss (all / excl. scripted occlusion)", f"{_fmt(s.get('target_loss_pct'))} % / {_fmt(s.get('target_loss_pct_excl_occlusion'))} %"),
        ("Lock retention", f"{_fmt(s.get('lock_retention_pct'))} %"),
        ("Re-acquisition times", ", ".join(_fmt(x) for x in rq) + " s" if rq else "no loss events"),
        ("False-lock frames", str(s.get("false_lock_frames", 0))),
        ("Settling time / rate saturation", f"{_fmt(s.get('settling_time_s'))} s / {_fmt(s.get('rate_saturation_pct'))} %"),
    ]
