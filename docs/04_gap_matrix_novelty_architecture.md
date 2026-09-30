# Innovation gap, novelty claims and final architecture — ANVESHA

**ANVESHA** (Sanskrit *anveṣaṇa*: search / quest) — *Belief-Driven Coarse Pointing, Acquisition & Tracking for mobile FSOC terminals.*

## 1. Research-family gap matrix
| Approach | Strengths | Weaknesses / limits | SIH requirement at risk | Opportunity |
|---|---|---|---|---|
| Global threshold + CoG | trivial, fast, sub-pixel when SNR high | no noise model; locks on any bright pixel (stars, S&P, rain); bias under background gradients | detection under noise/haze; false lock | CFAR on robust noise estimate |
| Blob / connected components | size/shape gating | threshold still ad hoc; fails at low SNR | fog/low light | matched filter before thresholding |
| Template / matched filter + CFAR (star-tracker, radar heritage) | optimal for known spot in white noise; constant false-alarm rate | needs noise estimate; impulsive noise violates Gaussian model | S&P 10 % | noise-type-adaptive pre-filter (switching median) |
| Optical flow (e.g. Wang et al. 2018, Opt. Express) | motion cue for beacon recognition | needs texture / frame pairs; jitter corrupts flow | jitter | use only for background registration (future) |
| CNN / YOLO / heat-map (DNANet, UIU-Net, TinyBeaconNet) | learns clutter rejection | domain shift; latency; often no measured gain vs CFAR for a square spot | FPS, credibility | use as *verifier* on few patches; measure gain by ablation |
| Siamese / correlation trackers (SiamRPN, KCF) | appearance tracking | beacon has no texture; drift under noise | centroid accuracy | not used (justify) |
| KF (CV) | standard, cheap | lag on manoeuvres; fixed R chases jitter | tracking error on fig-8/random | IMM + jitter-aware R |
| EKF / UKF | nonlinear models | measurement model here is linear in gimbal frame → little benefit | — | not needed (justify) |
| Particle filter / TBD | multimodal, low SNR | cost | FPS | belief *grid* used only during search |
| IMM (CV/CA/manoeuvre) | handles mixed motions | tuning | — | adopt (prior art — not claimed as novel) |
| PID on image error | simple | lag on ramps/circles; windup; ignores platform motion | error ≤10 px at speed | predictive FF control |
| MPC | constraints explicit | compute, model | — | time-optimal slew shaping gives constraint-aware behaviour at low cost |
| Disturbance observer / IMU feed-forward (ISP & FSM literature) | rejects platform motion before it appears in the image | needs inertial sensor | platform motion ±20 px/frame | IMU-aided gimbal-frame estimator (ablated) |
| Spiral / raster / Lissajous scan (FOU literature 2016–2026) | deterministic coverage, analysable | open-loop, ignores target motion & negative information, fixed FOV | acquisition ≤2 s, reacq ≤1 s | closed-loop Bayesian search |
| Probability-weighted scanning (TAES 2025 "probability-descent", elliptical FOU) | uses a prior | static prior, beam scanning, no recursive update, no FOV choice | — | recursive belief + planner |
| Info-theoretic PTZ sensor management (CV community) | principled look selection | surveillance context; not FSOC; no CFAR-based Pd model | — | transfer to FSOC coarse PAT with measured-noise Pd |
| Multi-field / wide-FOV acquisition (FSOC terminals) | faster acquisition | fixed switching; SNR penalty ignored | fog / low light | choose FOV from predicted Pd |
| Simulation-only studies | cheap, repeatable | fidelity questions | credibility | physics-informed disturbances, truth-based metrics, video mode |
| HIL testbeds | realism | expensive | — | clean hardware abstraction for future HIL |

## 2. Top-10 candidate innovations (screened)
| # | Innovation | Prior art | Novelty risk | Difficulty | Measurable benefit | Decision |
|---|---|---|---|---|---|---|
| 1 | **Recursive Bayesian belief-map acquisition** (negative information + motion diffusion) for the camera viewport | Koopman/Stone search theory; PTZ info-driven search; FOU scanning | Medium | Medium | acquisition time distribution vs spiral | **Core** |
| 2 | **Disturbance-aware adaptive FOV**: Pd(zoom) from measured noise σ and learned beacon contrast picks wide vs narrow FOV | multi-field acquisition; wide-FOV modes | Medium | Medium | acquisition under clear vs fog | **Core** |
| 3 | **Belief-seeded re-acquisition** from IMM predicted mean/cov with advection | Kalman coast; predicted search | Low–Medium | Low | reacq time vs spiral restart | **Core** |
| 4 | **Jitter-isolating measurement-noise estimator** (second-difference, robust) → loop does not chase jitter | adaptive KF (Mehra; fading KF for beacon tracking 2016) | Medium | Low | LOS error under jitter | **Core** |
| 5 | IMU-aided gimbal-frame estimator + platform-rate feed-forward | ISP/FSM disturbance FF literature | Low (known in stabilisation) | Low | error under platform motion | Adopt, ablate |
| 6 | Noise-type-adaptive MF-CFAR + CNN patch verifier | CFAR, star centroiding, CNN verifiers | Low | Low | false-lock / Pd under S&P, rain, distractors | Adopt, ablate |
| 7 | Manoeuvre re-anchor (strong verified off-gate detection re-initialises velocity) | track re-initiation | Low | Low | loss on abrupt reversals | Adopt |
| 8 | Honest error decomposition (image vs LOS vs centroid) in every log | — | n/a (engineering practice) | Low | credibility | Adopt |
| 9 | RL-learned search policy | DRL coarse-to-fine UAV tracking (T-ASE 2019) | Medium | High, data-hungry, hard to verify | uncertain | **Rejected** (not verifiable in time) |
| 10 | Event-camera PAT | event vision survey | n/a | hardware not in PS | none for PS | **Rejected** |

## 3. Novelty statements (defensible wording)
**Claim N1 — Belief-driven acquisition with disturbance-aware FOV.**
*Evidence:* our review of FSOC PAT (surveys: Kaymak 2018; Abdelfatah 2022; Eguri 2022), FOU scanning papers (2016–2026) and 20 public SIH26169 repositories found scanning patterns that are open-loop and fixed-FOV, and wide-FOV modes that are switched by rule. *Prior art:* search theory; info-theoretic PTZ sensor management; probability-weighted FOU scanning; multi-field acquisition. *Difference:* one recursive belief updated with negative information every frame, and FOV selected from a Pd model computed from the *measured* noise and learned beacon contrast. *Why it matters:* the PS asks for ≤2 s acquisition from a random start — infeasible for blind base-FOV scanning (§5 of doc 01). *Test:* acquisition-time distributions over seeded random starts vs spiral baselines, clear vs fog vs S&P.
Wording: "Based on our literature review, we did not identify a coarse-PAT system that ...".

**Claim N2 — One probabilistic state across search, track, coast and re-acquisition.** The same belief object is seeded by the tracker's prediction when the lock is lost. *Test:* re-acquisition time after scripted occlusions vs spiral restart.

**Claim N3 — Jitter-aware estimation.** White camera jitter is separated from smooth target motion via robust second differences; the estimator's R adapts, so the gimbal does not chase jitter. *Test:* LOS error vs jitter amplitude with/without the estimator.

Not claimed as novel: IMM, MF-CFAR, CNN verifier, IMU feed-forward, predictive control (all cited as prior art; our contribution is their integration and the measured ablation).

## 4. Final architecture
```
             ┌──────────────────── SIMULATION (240 Hz) ────────────────────┐
 Scenario ─► │ Screen/World ─ Beacon trajectory ─ Platform+IMU ─ Gimbal     │
 (YAML,seed) │         │ disturbances: jitter · turbulence · atmosphere ·   │
             │         ▼                                    noise           │
             │   Virtual FPA camera 640×480 @30 Hz (zoom 1×/2×/3×)         │
             └─────────┬──────────────────────────────▲────────────────────┘
      video .mp4 ──────┤ (Benchmark-2 bypass)          │ rate cmd (60 Hz)
                       ▼                               │
   PERCEPTION  noise-adaptive prefilter → matched filter → CFAR → IW-CoG
               → CNN verifier (ONNX) → candidates + frame noise stats
                       ▼
   ASSOCIATION gate (Mahalanobis) · shape · verifier · re-anchor
                       ▼
   ESTIMATION  IMM (CV/CA/MNV), gimbal frame, IMU input, jitter-aware R
                       ▼                           ▲
   SUPERVISOR  SEARCH → ACQUIRE(M-of-N) → TRACK → COAST → REACQUIRE
                       │                           │
   SEARCH      Belief map ◄── negative info ── Pd(zoom | measured noise)
               planner: argmax Pd·mass / time  → look point + zoom
                       ▼
   CONTROL     predictive: target-rate FF + IMU FF + latency comp + time-optimal slew, rate-limited
                       ▼
   METRICS (truth-only) → per-frame CSV · JSON summary · HTML/PDF report
   TELEMETRY → WebSocket → Mission-control GUI (camera · world+belief · telemetry · charts · events)
```
Separation of concerns: **simulation** (`sim/`), **disturbance** (`sim/disturbances.py`), **detection** (`perception/`), **tracking/estimation** (`estimation/`, `pat/`), **control** (`control/`), **evaluation** (`metrics/`, `bench/`). Ground truth flows only into metrics.

## 5. Baselines (same harness, same seeds)
* **A** — global threshold + CoG + PI(D), square spiral search, no estimator.
* **B** — median + blob + CoG + CV Kalman + PID, spiral.
* **C** — CNN heat-map detector + CV Kalman + PID, spiral.
* **ANVESHA** — MF-CFAR + CNN verifier + IMM + belief search/adaptive FOV + predictive control.
Baseline PID gains were tuned by grid search (kp∈{3,5,8,12}, ki∈{2,6,12,20}, kd∈{0,0.05}) on circular/figure-8/random runs; best (12, 20, 0.05) used for all baselines.
