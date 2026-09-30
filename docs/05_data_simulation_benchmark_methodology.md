# Data strategy · simulation methodology · benchmarking methodology

## A. Data strategy
### A.1 Real datasets considered
| Dataset / source | Class | Why |
|---|---|---|
| IR dim-small aircraft detection & tracking dataset (L083, China Scientific Data 2020) | PARTIALLY RELEVANT | small, dim, moving point-like targets; not optical beacons, IR not beacon-camera |
| Dense-Haze (L119) | METHODOLOGICALLY USEFUL | real haze appearance for validating the contrast/air-light model |
| Measured drone-to-ground FSO channel statistics (L027) | METHODOLOGICALLY USEFUL | real platform/pointing statistics to calibrate jitter/scintillation |
| Star-tracker / astronomy point-source imagery | METHODOLOGICALLY USEFUL | centroid-algorithm validation on real PSFs |
| Generic tracking / detection sets (VOT, COCO, AI-TOD L087) | NOT RELEVANT | textured objects; no FSOC beacon, no gimbal loop |
We found **no public dataset of beacon-camera frames from a coarse-pointing FSOC terminal with ground truth**. The PS itself states "Dataset link: NA", and the evaluators will supply their own videos.

### A.2 Physics-informed synthetic data (what we generate)
All data come from the same simulator used for evaluation, with deterministic seeds, and carry per-frame ground truth. Coverage (scenario files A–O + generator for training patches):
clean · Gaussian (σ≤20) · Poisson (0.3–3 photons/DN) · salt & pepper (≤15 %) · jitter (uniform/gaussian/sinusoidal ≤ ±20 px) · platform linear/circular/random/spiral/figure-8/vibration (≤ ±20 px/frame) · haze/fog/rain/low-light (severity 0–1) · turbulence (scintillation + angle-of-arrival wander) · slow→fast (≤400 px/s) · abrupt direction changes (random OU + wall reversals) · straight/circular/figure-8/random/spiral/sinusoidal/user trajectories · occlusions (target loss) · look-alike distractors and star fields · beacon sizes 5–20 px (training 2.5–20 px to cover zoom) · FOV 1×/2×/3× · perception latency (configurable).
Ground truth per frame (`frames.csv`): target x/y and velocity, LOS with/without jitter, pan/tilt and rates, platform offset, jitter, true beacon (u,v), visibility, occlusion, zoom, measured centroid, estimate, image/LOS/centroid/estimate errors, on-target & false-lock flags, confidence, SNR, processing time.

### A.3 Learned component data
BeaconNet (6.8 k parameters) is trained only on synthetic 64×64 patches from the same optics/disturbance code (`tools/train_beaconnet.py`, seeded). Held-out evaluation is on fresh synthetic patches (in-distribution) and is reported as such — it is **not** evidence of real-camera performance. Domain-shift mitigation: randomised noise/atmosphere/size per patch, per-patch robust normalisation, and the veto-only fusion rule (the network can lower but never raise the physics-based score).

### A.4 Sim-to-real plan
Record real beacon footage (LED/laser spot on a pan-tilt with a machine-vision camera) with a surveyed truth track; run it through Video mode; compare centroid statistics and adjust PSF, noise and atmosphere parameters (model calibration), then fine-tune BeaconNet with the real patches.

## B. Simulation methodology
* **Plant rates:** simulation 240 Hz · camera 30 Hz · control 60 Hz · GUI ≈30 Hz (multi-rate engine, `pat/engine.py`).
* **Geometry:** 1 screen px = 1 camera px at base zoom = 4°/640 = 0.00625° (109 µrad). Boresight = centre + gimbal + platform + jitter.
* **Image formation:** background radiance map (2000×2000) cropped by `warpAffine` at the boresight; beacon rendered analytically (box ⊗ Gaussian PSF, pixel-integrated) → exact sub-pixel truth; zoom = area-averaged background levels and a smaller beacon (constant surface brightness).
* **Atmosphere:** I = J·t + A(1−t) veil (haze/fog, cf. L118), forward-scatter blur (fog), rain streaks, low-light gain; turbulence: log-normal scintillation (AR(1)) + angle-of-arrival wander.
* **Sensor:** Poisson shot → Gaussian read → 8-bit quantisation → salt & pepper.
* **Gimbal:** rate command → actuator latency → rate saturation → acceleration limit → first-order rate loop → travel limits.
* **Platform + IMU:** LOS disturbance models; gyro with noise and bias.
* **Determinism:** `SeedSequence(seed).spawn(8)` → independent PCG64 streams per subsystem → bit-identical re-runs (tested).
* **Separation of truth:** the tracker only receives frames, encoder angles, IMU rates and timestamps.

## C. Benchmarking methodology
* **Matrix:** 16 scenarios × 4 pipelines (A threshold+PID, B blob+KF+PID, C CNN+KF+PID, ANVESHA) × 3 seeds, 20 s each; identical seeds per pipeline. Ablation: ANVESHA with one component removed (belief search, zoom, IMU FF, jitter-aware R, CNN verifier, IMM→KF) on 10 scenarios.
* **Baseline fairness:** baseline PID gains tuned by grid search (kp 3–12, ki 2–20, kd 0–0.05) and the best set used; baselines share the simulator, metrics and seeds.
* **Metric definitions:** in `anvesha/metrics/metrics.py` docstring (acquisition, image/LOS error, centroid error, loss with/without scripted occlusion, lock retention, re-acquisition per loss episode incl. unrecovered, false-lock frames, processing time, loop FPS, settling, rate saturation).
* **Reporting:** mean over seeds (+max where relevant); PS pass/fail flags per run; everything regenerated by `run_benchmark.bat`.
* **Benchmark-2 rehearsal:** generated 2000×2000 30 fps mp4 + truth CSV; video mode logs raw per-frame centroid (for centroiding error) and filtered estimate separately.
* **What results mean:** software-in-the-loop measurements on a 2-core cloud CPU; not hardware results.
