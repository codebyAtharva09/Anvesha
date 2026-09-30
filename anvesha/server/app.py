"""Mission-control server: FastAPI + WebSocket telemetry.

A single Engine instance runs in a background task, paced to wall-clock time.
Every camera frame produces one telemetry record; the camera image is sent as
JPEG (binary WS message) and the world/belief state at a lower rate. The GUI
only *displays* engine state - there is no separate mock data path.
"""
from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import config as C
from ..bench.runner import ROOT, SCEN_DIR, build_cfg
from ..pat.engine import Engine
from ..sim.platform import PlatformMotion
from ..sim import trajectories as trj

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
RESULTS = ROOT / "results"


class Session:
    def __init__(self):
        self.eng: Optional[Engine] = None
        self.running = False
        self.speed = 1.0
        self.lock = threading.Lock()
        self.meta: Dict[str, Any] = {}
        self.video_job: Dict[str, Any] = {"state": "idle"}

    def start(self, scenario: str, pipeline: str, seed: int, overrides: Optional[Dict] = None, duration: float = 600):
        cfg = build_cfg(scenario, pipeline, seed, duration)
        for k, v in (overrides or {}).items():
            C.set_dotted(cfg, k, v)
        C.validate(cfg)
        with self.lock:
            self.eng = Engine(cfg)
            self.running = True
            self.meta = {"scenario": scenario, "pipeline": pipeline, "seed": seed,
                         "run_id": f"{scenario}-{pipeline}-s{seed}-{time.strftime('%H%M%S')}"}

    def set_live(self, key: str, value):
        """Change a disturbance / target parameter while running."""
        if not self.eng:
            return
        cfg = self.eng.cfg
        C.set_dotted(cfg, key, value)
        w = self.eng.world
        sec = key.split(".")[0]
        if sec in ("noise", "atmosphere"):
            w.dist.reconfigure(cfg.noise, cfg.atmosphere)
        elif sec == "platform":
            p = cfg.platform
            w.platform = PlatformMotion(p.motion, p.amplitude_px_per_frame, cfg.camera.rate_hz, p.period_s,
                                        p.vibration_hz, w.rng_plat)
        elif key in ("target.trajectory", "target.speed_px_s"):
            cur = w.targets[0].pos.copy()
            w.targets[0] = trj.make(cfg.target.trajectory, w.W, w.H, cfg.target.speed_px_s, w.rng_traj, tuple(cur),
                                    cfg.target.radius_px)
        elif key == "search.allow_zoom":
            s = self.eng.sup
            s.planner.zooms = cfg.camera.zoom_levels if cfg.search.allow_zoom else [1.0]


S = Session()


def _telemetry(eng: Engine) -> Dict:
    rep, tr, w, sup = eng.last_report, eng.last_truth, eng.world, eng.sup
    dpp = eng.cfg.deg_per_px
    m = eng.metrics
    lo = m.rows[-1] if m.rows else None
    fps = 1000.0 / max(np.mean(eng.loop_ms), 1e-3) if eng.loop_ms else 0.0
    d = {
        "t": round(w.t, 3), "mode": sup.mode, "zoom": w.zoom,
        "pan_deg": round(float(w.gimbal.angle[0] * dpp), 4), "tilt_deg": round(float(w.gimbal.angle[1] * dpp), 4),
        "pan_rate": round(float(w.gimbal.rate[0] * dpp), 3), "tilt_rate": round(float(w.gimbal.rate[1] * dpp), 3),
        "cmd": [round(float(x * dpp), 3) for x in eng.last_cmd],
        "rate_lim": [eng.cfg.gimbal.max_pan_rate_dps, eng.cfg.gimbal.max_tilt_rate_dps],
        "fps": round(fps, 1),
        "proc_ms": round(rep.proc_ms, 2) if rep else 0,
        "conf": round(rep.confidence, 3) if rep else 0,
        "snr": round(rep.chosen.snr, 1) if (rep and rep.chosen) else None,
        "ndet": len(rep.detections) if rep else 0,
        "meas": [round(rep.chosen.u, 2), round(rep.chosen.v, 2)] if (rep and rep.chosen) else None,
        "cands": [[round(x.u, 1), round(x.v, 1), round(x.score, 2)] for x in (rep.detections[:8] if rep else [])],
        "pred_uv": None, "gate_px": None,
        "imm": [round(x, 3) for x in rep.imm_mu] if (rep and rep.imm_mu) else None,
        "imm_names": sup.est.names if sup.est is not None else None,
        "pd": round(rep.pd, 3) if rep else None,
        "noise_sigma": round(rep.stats.pix_sigma, 2) if rep else None,
        "sp_frac": round(rep.stats.sp_frac, 3) if rep else None,
        "jit_sigma": round(sup.est.jitter_sigma, 2) if sup.est is not None else None,
        "nis": round(rep.nis, 2) if rep else None,
        "truth": {
            "err_img": round(lo[COL["err_img_px"]], 2) if lo else None,
            "err_los": round(lo[COL["err_los_px"]], 2) if lo else None,
            "cent_err": None if (lo is None or np.isnan(lo[COL["centroid_err_px"]])) else round(lo[COL["centroid_err_px"]], 3),
            "on_target": bool(lo[COL["on_target"]]) if lo else False,
            "visible": bool(tr.visible) if tr else False,
            "beacon_uv": [round(float(tr.beacon_uv[0]), 2), round(float(tr.beacon_uv[1]), 2)] if tr else None,
        },
        "events": list(rep.events) if rep else [],
    }
    if sup.est is not None and sup.est.initialised and rep is not None:
        g = sup.est.x[:2]
        uv = sup.to_uv(g, w.gimbal.angle, w.zoom)
        d["pred_uv"] = [round(float(uv[0]), 1), round(float(uv[1]), 1)]
        d["gate_px"] = round(float(3 * np.sqrt(max(np.trace(sup.est.P[:2, :2] + sup.est.R()) / 2, 0)) / w.zoom), 1)
    return d


COL = {n: i for i, n in enumerate(__import__("anvesha.metrics.metrics", fromlist=["COLUMNS"]).COLUMNS)}


def _world(eng: Engine) -> Dict:
    w, sup = eng.world, eng.sup
    b = sup.bm.b
    bb = (b / max(b.max(), 1e-12) * 255).astype(np.uint8)
    small = cv2.resize(bb, (40, 40), interpolation=cv2.INTER_AREA)
    tr = eng.last_truth
    return {
        "W": w.W, "H": w.H,
        "target": [round(float(w.targets[0].pos[0]), 1), round(float(w.targets[0].pos[1]), 1)],
        "others": [[round(float(o.pos[0]), 1), round(float(o.pos[1]), 1)] for o in w.targets[1:]],
        "bore": [round(float(x), 1) for x in (w.center + w.gimbal.angle + w.platform.offset)],
        "bore_g": [round(float(x), 1) for x in (w.center + w.gimbal.angle)],
        "fov": [eng.cfg.camera.width_px * w.zoom, eng.cfg.camera.height_px * w.zoom],
        "plan": [round(float(x), 1) for x in sup.plan_xy] if sup.plan_xy is not None else None,
        "platform": [round(float(x), 1) for x in w.platform.offset],
        "belief": base64.b64encode(small.tobytes()).decode(),
        "belief_shape": [40, 40],
        "search": sup.search_kind,
        "occluded": bool(tr.occluded) if tr else False,
    }


def create_app():

    app = FastAPI(title="ANVESHA")
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
    RESULTS.mkdir(exist_ok=True)
    app.mount("/results", StaticFiles(directory=str(RESULTS)), name="results")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/scenarios")
    def scenarios():
        out = []
        import yaml
        for p in sorted(SCEN_DIR.glob("*.yaml")):
            d = yaml.safe_load(p.read_text()) or {}
            out.append({"id": p.stem, "description": d.get("description", "")})
        return out

    @app.get("/api/config")
    def get_config():
        return S.eng.cfg.to_dict() if S.eng else C.Config().to_dict()

    @app.get("/api/summary")
    def summary():
        return JSONResponse(json.loads(json.dumps(S.eng.metrics.summary(), default=lambda o: None)) if S.eng else {})

    @app.post("/api/report")
    def report():
        if not S.eng:
            return {"error": "no run"}
        from ..metrics.logger import write_run
        with S.lock:
            s = S.eng.metrics.summary()
            d = RESULTS / "gui_runs" / S.meta.get("run_id", "run")
            write_run(d, S.eng.cfg, S.eng, s)
        rel = d.relative_to(RESULTS).as_posix()
        return {"html": f"/results/{rel}/report.html", "pdf": f"/results/{rel}/report.pdf", "csv": f"/results/{rel}/frames.csv"}

    @app.get("/api/bench")
    def bench():
        out = {}
        for name in ("bench", "ablation"):
            p = RESULTS / name / "summary.json"
            if p.exists():
                out[name] = json.loads(p.read_text())
        return out

    @app.post("/api/video")
    async def video(body: dict):
        path = body.get("path")
        truth = body.get("truth") or None
        if not path or not Path(path).exists():
            return {"error": f"file not found: {path}"}
        from ..video.runner import run_video
        out = RESULTS / "video" / Path(path).stem
        S.video_job = {"state": "running", "path": path}

        def job():
            try:
                s = run_video(path, str(out), truth, float(body.get("beacon_size", 10)))
                S.video_job = {"state": "done", "summary": s, "csv": f"/results/video/{Path(path).stem}/video_frames.csv"}
            except Exception as e:  # pragma: no cover
                S.video_job = {"state": "error", "error": str(e)}
        threading.Thread(target=job, daemon=True).start()
        return {"ok": True}

    @app.get("/api/video")
    def video_status():
        return json.loads(json.dumps(S.video_job, default=lambda o: None))

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        stop = asyncio.Event()

        async def reader():
            try:
                while True:
                    msg = json.loads(await sock.receive_text())
                    c = msg.get("cmd")
                    try:
                        if c == "start":
                            S.start(msg.get("scenario", "A_clean"), msg.get("pipeline", "anvesha"), int(msg.get("seed", 1)),
                                    msg.get("overrides"))
                        elif c == "pause":
                            S.running = False
                        elif c == "resume":
                            S.running = True
                        elif c == "set":
                            with S.lock:
                                S.set_live(msg["key"], msg["value"])
                        elif c == "occlude" and S.eng:
                            S.eng.world.manual_occlusion = bool(msg.get("on"))
                        elif c == "speed":
                            S.speed = float(msg.get("value", 1))
                        elif c == "kick" and S.eng:
                            # inject a sudden LOS disturbance (e.g. platform shock)
                            S.eng.world.gimbal.angle += np.array(msg.get("px", [300, -200]), float)
                        await sock.send_text(json.dumps({"type": "ack", "cmd": c, "meta": S.meta}))
                    except Exception as e:
                        await sock.send_text(json.dumps({"type": "error", "error": str(e)}))
            except WebSocketDisconnect:
                stop.set()
            except Exception:
                stop.set()

        async def writer():
            last_wall = time.perf_counter()
            k = 0
            while not stop.is_set():
                await asyncio.sleep(1 / 60)
                now = time.perf_counter()
                dt_wall = min(now - last_wall, 0.1)
                last_wall = now
                if not (S.eng and S.running):
                    continue
                frames = []
                with S.lock:
                    eng = S.eng
                    target_t = eng.world.t + dt_wall * S.speed
                    while eng.world.t < target_t:
                        rep = eng.step()
                        if rep is not None:
                            frames.append(rep)
                    if not frames:
                        continue
                    k += 1
                    tel = _telemetry(eng)
                    img = eng.last_frame
                    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    wd = _world(eng) if k % 3 == 0 else None
                    evs = []
                    for r in frames:
                        evs += r.events
                tel["events"] = evs
                tel["meta"] = S.meta
                try:
                    await sock.send_text(json.dumps({"type": "tel", "d": tel}, default=float))
                    if ok:
                        await sock.send_bytes(jpg.tobytes())
                    if wd is not None:
                        await sock.send_text(json.dumps({"type": "world", "d": wd}))
                except Exception:
                    stop.set()

        await asyncio.gather(reader(), writer())

    return app


def serve(port: int = 8765, open_browser: bool = True):
    import uvicorn
    app = create_app()
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
