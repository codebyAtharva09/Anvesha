# SIH26169 — Problem-statement decomposition & compliance matrix

Source: official PS PDF (`26169.pdf`, "Problem Statement 4"), Department of Space / ISRO, Category Software, Theme Smart Automation / Space Technology.

## 1. What the PS actually asks for (one sentence)
A standalone software system that **autonomously detects, identifies and continuously tracks one designated moving beacon in a virtual scene by steering a rate-limited virtual pan/tilt camera viewport**, under noise, jitter, platform motion and atmospheric degradation — **and** that can bypass its own camera to run the same coarse-pointing chain on **evaluator-supplied .mp4 videos (30 fps, full screen)**, logging centroiding error and performance automatically.

## 2. Hidden-but-decisive items (easy to miss)
| # | Item | Why it matters | Where handled |
|---|------|----------------|---------------|
| H1 | **Benchmark-2 = 30 % of marks**: evaluator `.mp4` videos covering the complete screen; software must *bypass its PTZ camera* and log **centroiding error** vs predefined values | A camera-only simulator scores zero here. Centroid precision on full 2000×2000 noisy frames becomes the dominant metric | `anvesha/video/` video mode (full-frame + ROI), per-frame raw-measurement log separated from filtered estimate |
| H2 | **Benchmark-1 = 30 %**: "Log of centroiding error" + auto-generated performance logs | Logs must be produced automatically, per frame | `metrics/`, `report/` |
| H3 | Acquisition ≤ 2 s with default 4°×3° FOV, 5 °/s pan, random start on a 2000 px (=12.5°) screen | Blind raster/spiral at base FOV cannot cover 12.5°×12.5° in 2 s at 5 °/s — a physics limit, not a tuning issue (see §5) | Belief-driven search with disturbance-aware adaptive FOV |
| H4 | Jitter up to ±20 px/frame vs tracking error ≤ 10 px | Uniform ±20 px jitter alone is ≈11.5 px RMS per axis (≈16 px radial). A coarse gimbal cannot cancel white frame-to-frame jitter; must be reported honestly and separated from correctable LOS error | Metrics report both image-plane error (incl. jitter) and LOS error (excl. jitter); estimator isolates jitter |
| H5 | Platform motion up to ±20 px/frame (= 600 px/s = 3.75 °/s at 30 Hz) with 5 °/s gimbal | Leaves only 1.25 °/s margin for target motion — rate saturation and feed-forward matter | IMU feed-forward + rate-limit-aware control |
| H6 | "Identifies" the *designated* target; multiple targets optional | Distractor rejection / association needed | Gated association, CNN verifier, shape tests |
| H7 | Deliverables: standalone executable, documented modular code, 10–15 page technical report, user manual, performance log, optional 3–5 min video | Must plan packaging + docs from day 1 | `packaging/`, `docs/` |
| H8 | Technical evaluation (20 %) explicitly scores **Innovation and Novelty** and **AI and computer vision** | AI must earn its place with measured value | Ablations in benchmark suite |

## 3. Compliance matrix
| Req | PS wording | Our implementation | Verification | Metric | PPT evidence | Module |
|---|---|---|---|---|---|---|
| F1 | Generate a configurable virtual environment | 2000×2000 (min) screen; background dark-sky / starfield / clutter / uniform; distractors; all YAML-configurable & validated | Scenario files A–N load and run | runs pass validation | Scenario matrix | `sim/optics.py`, `config.py` |
| F2 | Generate one or more moving targets | 1 designated beacon (+ optional extra look-alike targets); square/circle/gaussian; 5–20 px | Unit + scenario | truth logs | GUI screenshot | `sim/trajectories.py`, `sim/world.py` |
| F3 | ≥4 motions: straight, circular, figure-8, random (+spiral, sinusoidal, user) | All 7 implemented (random = Ornstein–Uhlenbeck manoeuvres) | Benchmark per trajectory | error vs trajectory | chart | `sim/trajectories.py` |
| F4 | Movable virtual camera, 640×480, FOV 4°×3° default, ≥30 Hz, mono FPA, start at centre | Camera renders a viewport of the screen at boresight; configurable res/FOV/rate; zoom levels (adaptive FOV) | Config tests | frame rate | GUI | `sim/world.py` |
| F5 | Pan/tilt 5–10 °/s, update ≥20 Hz | Rate-commanded gimbal with rate saturation, accel limit, lag, latency, travel limits; control at 60 Hz | Saturation logged | rate RMS, % saturated | control chart | `sim/platform.py`, `control/` |
| F6 | Detect target automatically | MF-CFAR detector + CNN verifier (+ 3 baseline detectors) | Detection logs | Pd / false-lock | ROC/ablation | `perception/` |
| F7 | Track continuously using CV | ROI tracking + IMM estimator + gated association + coast/re-anchor | Loss/retention metrics | loss %, retention | table | `estimation/`, `pat/` |
| F8 | Control & reposition the camera | Predictive controller (target-rate FF, IMU FF, latency comp.) | closed loop | settling, error | plot | `control/` |
| F9 | Disturbances: atmospheric turbulence, platform vibration, camera motion, noise | Clear/haze/fog/rain/low-light; scintillation+AoA wander; platform linear/circular/random/spiral/fig-8/vibration; jitter uniform/gaussian/sinusoidal; S&P (~10 %), Gaussian (σ≤20), Poisson | Scenario B–N | metrics per disturbance | robustness chart | `sim/disturbances.py`, `sim/platform.py` |
| F10 | Display tracking performance & statistics in real time | Web mission-control GUI fed by WebSocket from the same engine | Live demo | FPS, errors, state | screenshot | `server/`, `ui/` |
| P16 | Acquisition ≤ 2 s | Belief-driven search + adaptive FOV | Monte-Carlo random starts | acquisition time distribution | bar chart | `search/belief.py` |
| P17 | Tracking error ≤ 10 px | IMM + predictive control; error split image/LOS | Benchmarks | mean/RMS/max | table | `metrics/` |
| P18 | Target loss < 5 % | Coast + re-anchor + association | Benchmarks | loss % | table | `pat/` |
| P19 | Re-acquisition ≤ 1 s | Belief seeded from IMM prediction | Occlusion scenarios | reacq time | chart | `search/`, `pat/` |
| P20 | ≥ 20 FPS | ROI processing, vectorised OpenCV, 1 ms CNN verifier | Wall-clock timing | FPS mean/min | table | all |
| D1 | Standalone executable | PyInstaller spec + launcher (`packaging/`) — build on Windows | Build script | — | — | `packaging/` |
| D2 | Modular, commented source | Package layout per concern | Code review | — | repo tree | repo |
| D3 | Technical report 10–15 pp | Outline + auto-inserted measured tables | — | — | — | `docs/` |
| D4 | User manual | Outline | — | — | — | `docs/` |
| D5 | Performance log (duration, FPS, acq. time, avg/max error, lock retention, processing time) | Per-frame CSV + JSON summary + HTML report with charts, auto-generated each run | Every run | all | report screenshot | `metrics/`, `report/` |
| B2 | Video (.mp4) input bypassing PTZ | Video mode: full-frame acquisition → ROI tracking, per-frame centroid log; optional virtual gimbal over video | Self-generated videos with truth CSV | centroid RMSE, FPS | table | `video/` |

## 4. Parameter table (defaults = PS reference)
Screen 2000×2000 · camera 640×480 mono · FOV 4°×3° (1 px = 0.00625° = 109 µrad) · 30 Hz · start centre · beacon square 10×10 (5–20) · random initial location · pan/tilt 5 °/s (5–10) · control 60 Hz (≥20) · S&P 10 % · Gaussian σ ≤ 20 · jitter ≤ ±20 px/frame · platform ≤ ±20 px/frame · atmosphere clear/haze/fog/rain/low-light.

## 5. Feasibility arithmetic (why acquisition is hard)
* Screen 2000 px × 0.00625 °/px = **12.5° × 12.5°**. Base FOV 4°×3° covers **7.7 %** of it.
* Gimbal 5 °/s ⇒ in 2 s the boresight can move ≤ 10°. A raster covering 12.5°×12.5° with 4°×3° tiles needs ~13–17 tiles and ≈ 40–50° of slew ⇒ **~8–10 s worst case** for blind search at base FOV.
* Therefore ≤ 2 s acquisition from an arbitrary start *requires* either (a) a wider acquisition FOV (PS allows "user-defined" FOV) or (b) prior information. ANVESHA does (a) in a principled, disturbance-aware way and (b) for re-acquisition. Competing public repos independently observed the same limit (e.g. one reports 6.67 s mean acquisition in a "4° only" configuration).
