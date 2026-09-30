# ANVESHA — Belief-Driven Coarse Pointing, Acquisition & Tracking for Mobile FSOC Terminals

**Smart India Hackathon 2026 · SIH26169 · ISRO / Department of Space · Team Regnum Carya**

ANVESHA is a software-in-the-loop coarse-PAT system: a configurable virtual 2000×2000 scene with a moving optical beacon, a rate-limited virtual pan/tilt FPA camera (640×480, 4°×3°, 30 Hz) and a closed-loop tracker that detects, identifies and continuously tracks the beacon under noise, jitter, platform motion and atmospheric degradation — plus a Benchmark-2 mode that bypasses the virtual camera and runs on evaluator `.mp4` videos. All performance numbers are computed from simulation ground truth.

```
camera → noise-adaptive matched filter + CFAR → sub-pixel IW-CoG → CNN verifier (veto)
      → gated association → IMM estimator (gimbal frame, IMU input, jitter-aware noise)
      → PAT supervisor (SEARCH · ACQUIRE · TRACK · COAST · REACQUIRE)
      → joint belief over beacon position × detectability → look planner (pointing + FOV)
      → predictive controller (target-rate & IMU feed-forward, latency compensation) → gimbal
```

## Quick start (Windows)
```
install.bat            # pip install -r requirements.txt  (Python 3.10+)
run_gui.bat            # mission-control GUI at http://127.0.0.1:8765
run_benchmark.bat      # 16 scenarios × 4 pipelines × 3 seeds + ablation → results\bench, results\ablation
run_video.bat my.mp4 [truth.csv]   # Benchmark-2: evaluator video, PTZ bypassed
run_real_footage.bat clip.mp4 [size]  # real phone clip of a moving LED -> results\real_footage
train_gpu.bat          # retrain BeaconNet on an NVIDIA GPU (optional)
packaging\build_exe.bat  # standalone ANVESHA.exe (PyInstaller)
```
CLI: `python -m anvesha {gui|run|bench|ablate|make-video|video} --help` · tests: `python -m pytest -q`

## Repository
| Path | Content |
|---|---|
| `anvesha/sim/` | world, trajectories (7), optics/image formation, disturbances, platform + IMU + gimbal |
| `anvesha/perception/` | detectors (threshold / blob / CNN / MF-CFAR / fusion), sub-pixel centroiding, BeaconNet (ONNX) |
| `anvesha/estimation/` | KF / IMM with jitter-aware measurement noise |
| `anvesha/search/` | joint position–detectability belief, look planner, spiral/raster baselines |
| `anvesha/control/` | PID (baselines), predictive controller |
| `anvesha/pat/` | supervisor (mode machine) and multi-rate engine |
| `anvesha/metrics/`, `anvesha/report/` | truth-based metrics, logs, automatic HTML/PDF reports |
| `anvesha/bench/` | benchmark & ablation runner |
| `anvesha/video/` | Benchmark-2 video mode |
| `anvesha/server/`, `anvesha/ui/` | FastAPI/WebSocket server, mission-control web GUI (2D + 3D) |
| `configs/scenarios/` | scenarios A–O (clean, noise types, jitter, platform, fog, haze, rain, low light, fast, occlusion, combined, worst case, distractors) |
| `docs/` | PS compliance matrix, SOTA report, 134-paper literature DB, competitor analysis, gap/novelty/architecture, methodology, judge Q&A, outlines & checklist, readiness matrix |
| `ppt/` | SIH idea deck (template), presenter script, red-team review |
| `results/` | benchmark, ablation and video-mode outputs |

## Honesty notes
Simulation prototype — not flight software. Image-plane error includes camera jitter (uncorrectable by a coarse gimbal); LOS error excludes it; both are logged. The learned verifier is trained and evaluated on synthetic data only.
