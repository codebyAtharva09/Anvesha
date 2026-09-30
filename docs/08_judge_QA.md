# 55 hard evaluator questions — evidence-based answers

Numbers quoted as "measured" come from `results/bench/summary.json`, `results/ablation/summary.json` and `results/video_M6/video_summary.json` (software-in-the-loop, 3 seeds). Re-run `run_benchmark.bat` to regenerate.

**Concept & novelty**
1. **Why AI?** Only where it measurably helps: a 6.8 k-parameter CNN verifier (<1 ms per frame on CPU) that can *lower* confidence for streaks, impulse clusters and clutter. The main intelligence is probabilistic (Bayesian search, IMM). The ablation (`abl_no_cnn`) shows its contribution — we report it even if small.
2. **Why not just centroiding?** We do centroid (iterative windowed CoG) — but centroiding answers "where is the spot in this frame", not "where should the camera look" or "is this the beacon". Baseline A is thresholding + CoG + PID; compare in the benchmark table.
3. **Why not optical flow?** A featureless spot on a dark background gives little flow signal, and jitter/noise corrupt it. Flow is useful for background registration (future work, L060).
4. **Why not a plain Kalman filter?** Mixed motions (circular, figure-8, random manoeuvres) need a model set; IMM switches between CV/CA/manoeuvre models. Ablation `abl_kf_cv` quantifies it.
5. **Why not PID?** PID on image error lags ramps/circles and chases jitter. Our controller feeds forward estimated target rate and IMU platform rate, compensates latency and shapes slews time-optimally. Baselines use a grid-tuned PID.
6. **What exactly is novel?** Not the detector or filter. The claim is the search layer: one recursive belief over *position and beacon detectability* that is updated with negative information every frame, chooses pointing *and* FOV by expected detection rate, and seeds re-acquisition from the tracker's prediction. "Based on our review of 134 papers and 20 public SIH26169 repositories, we did not identify…"
7. **Which papers are closest?** Probability-ordered FOU scanning (L049, TAES 2025), FOU-shaped scans (L050), multi-field acquisition (L131, L132), information-theoretic PTZ sensor management (L133), search theory (Koopman/Stone). We cite them and differ by recursion + detectability-aware FOV choice + re-use for re-acquisition.
8. **Isn't wide-FOV acquisition just "zoom out"?** A fixed zoom-out fails in fog/noise where a small beacon becomes undetectable. The planner computes Pd per FOV from the measured noise and a posterior over beacon contrast; in clear air it zooms out, in fog it learns (from misses) that the beacon is faint and stays narrow. The G_fog scenario shows this.

**Acquisition / re-acquisition**
9. **How is acquisition time defined?** From run start to the first frame where the system is in TRACK and the true LOS error ≤ 10 px (truth-based, not self-reported).
10. **Can blind scanning meet ≤2 s?** Not from an arbitrary start at 4°×3°/5 °/s over 12.5°×12.5°: coverage needs ≈8–10 s worst case (doc 01 §5). Measured baseline spiral acquisition times confirm this.
11. **Is changing FOV allowed?** PS lists FOV as "User-defined, default 4°×3°". Adaptive FOV can be disabled (`search.allow_zoom=false`); the belief planner still orders base-FOV looks optimally (ablation `abl_no_zoom`).
12. **What happens when the beacon disappears?** TRACK → COAST (prediction-only, gate widened) → after 0.6 s or when uncertainty exceeds the FOV → REACQUIRE: the belief is seeded from the IMM mean/covariance (+ velocity advection), and the planner looks where the beacon most probably is.
13. **Re-acquisition time definition?** Per loss episode, from loss (or from the end of a scripted occlusion) to the next on-target frame; unrecovered losses are counted separately, never hidden.
14. **What if the target leaves the FOV?** Same COAST → REACQUIRE path; the gate in COAST is widened ×4 and a strong verified detection close to the prediction re-anchors the track.
15. **How does FOV affect acquisition probability?** Coverage ∝ zoom², beacon size ∝ 1/zoom → matched-filter SNR ∝ 1/zoom. The planner maximises Pd(zoom)·mass(footprint)/time.

**Detection & robustness**
16. **How do you distinguish beacon from noise?** Noise-type-adaptive pre-filter (median sized by measured impulse fraction), matched filter, CFAR threshold on a robust (MAD) noise estimate, shape tests (size, elongation), CNN veto, M-of-N temporal confirmation, and gating by the prediction.
17. **Multiple bright objects?** Association gate + score; during acquisition the strongest beacon-like return is preferred; a lock that stays static (the designated target is moving) is rejected and blacklisted (scenario O). Limitation: a *moving* look-alike of identical brightness cannot be distinguished from one frame — beacon modulation (supported via `target.blink_hz`) is the standard fix.
18. **Fog?** Contrast loss + air-light veil removed by local background subtraction; forward-scatter blur handled by the matched filter; FOV choice adapts. Scenario G.
19. **Vibration?** Platform motion within the gimbal bandwidth is cancelled by IMU feed-forward; vibration above the gimbal bandwidth (e.g. 13 Hz) cannot be removed by a coarse gimbal and shows up as LOS error — that is the fine stage's job (FSM). Scenario F2 is reported honestly.
20. **Low SNR?** CFAR keeps false alarms constant; M-of-N confirmation; Pd model reduces reliance on wide FOV.
21. **Higher target velocity?** Error grows with manoeuvre intensity (scenario J); pan/tilt rate limits (5 °/s = 800 px/s) bound what any controller can follow.
22. **How do you guarantee ≤10 px?** We don't "guarantee" — we measure. In most scenarios LOS error is well below 10 px; where it isn't (vibration, very fast manoeuvres, jitter) the tables show it and explain the physics.
23. **±20 px jitter vs ≤10 px?** Uniform ±20 px white jitter alone is ≈11.5 px RMS per axis (≈16 px radial). No coarse gimbal can cancel white frame-to-frame jitter; we report image-plane error (incl. jitter) and LOS error (correctable) separately and avoid chasing jitter via the jitter-aware estimator.
24. **Unseen disturbances?** Robust statistics (MAD, CFAR) and hypothesis-based Pd adapt online; the benchmark includes combined and worst-case scenarios not used for tuning.
25. **Domain shift for the CNN?** Veto-only fusion: if the CNN misbehaves it can only reduce confidence; the classical chain still works (ablation `abl_no_cnn`).

**Estimation & control**
26. **Controller input/output?** Input: IMM state (gimbal-frame position/velocity), gimbal encoder angle/rate, IMU platform rate. Output: pan/tilt rate commands, saturated at the PS limits.
27. **Stability?** Loop gain 6 s⁻¹ with ≈70 ms total modelled lag gives ≈40° phase margin (engineering estimate); no integrator (no wind-up); time-optimal slew profile respects acceleration limits (no overshoot at saturation). Settling time and rate saturation are logged.
28. **Actuator saturation?** Commands clipped to 5 °/s; rate/accel limits simulated in the plant; saturation % logged per run.
29. **Latency?** Perception latency is configurable; the controller predicts to t+τ (actuator + rate-loop + half frame + perception).
30. **Role of uncertainty?** Gate size, COAST termination, re-acquisition prior and confidence all come from the estimator covariance; search from the belief.
31. **Why EKF/UKF not used?** In the gimbal frame the measurement model is linear; nonlinear filters add cost without benefit here (documented in the gap matrix).

**Simulation & evaluation**
32. **Ground truth?** Exact analytic beacon position in every frame (sub-pixel), gimbal/platform/jitter states — logged per frame.
33. **How is synthetic data generated?** Same image-formation and disturbance code as the benchmark, seeded; see doc 05.
34. **Why should synthetic represent reality?** Models follow standard physics (box⊗PSF, Poisson–Gaussian sensor noise, air-light haze model, log-normal scintillation); they are parameterised and will be calibrated on real footage (doc 05 A.4). We claim simulation results only.
35. **How do you validate the simulator?** Unit tests (sub-pixel truth, noise statistics, determinism), consistency checks (image vs LOS error), and the planned real-footage calibration.
36. **Reproducibility?** Seeds + config snapshot stored with every run; bit-identical re-runs are unit-tested.
37. **Overfitting?** Parameters were tuned on a few clean runs (seed 3, center start); benchmarks use seeds 1–3, random starts and 16 scenarios; worst-case scenarios were not used for tuning.
38. **Computational complexity?** Per frame: O(N) image filters on 640×480 (or ROI), CNN on ≤8 32×32 patches, IMM 3×6-state, belief planner on an 80×80 grid × 4 contrast layers × 3 zooms (box filters). Measured processing time and FPS in the tables.
39. **Worst-case latency?** p95 and max processing time are logged per run (see benchmark report).
40. **≥20 FPS guaranteed?** Measured loop FPS (render + track) is well above 20 on a 2-core CPU in most scenarios; the lowest values occur with Poisson noise (rendering cost) — see tables.
41. **Detection accuracy vs FPS?** ROI processing while tracking; full-frame only when needed; CNN only on candidate patches.
42. **FOV vs pixel resolution trade-off?** Wider FOV → coarser angular resolution and lower SNR; hence zoom back to base FOV for tracking and centroiding.

**Benchmark-2 video**
43. **How do you handle the evaluator's mp4?** `run_video.bat file.mp4` — full-frame acquisition, ROI tracking with IMM, per-frame RAW centroid log (for centroiding error) + filtered estimate, FPS, acquisition, lock retention; optional truth CSV.
44. **Why log raw centroid, not the filtered estimate?** Under jitter the true beacon jumps frame to frame; a filter would lag and inflate centroiding error. Our rehearsal shows the raw centroid error far below the estimate error.

**System & future**
45. **Hardware integration?** The tracker only exchanges frames, encoder/IMU readings and rate commands with the world — the same interface a camera SDK + pan-tilt driver provides; swap `SimWorld` for a hardware adapter.
46. **What part is implemented?** Everything in the architecture diagram except the Windows .exe build (spec provided) and hardware adapters; see readiness matrix.
47. **Measured vs proposed?** Tables are measured; roadmap items (HIL, real footage, FSM hand-off) are proposed and labelled as such.
48. **Why would ISRO need this?** Hardware-free, repeatable development and regression testing of coarse PAT algorithms under controlled disturbances; training; pre-screening algorithms before HIL/field trials.
49. **What would you do with real ISRO hardware?** Calibrate the image/noise model on the terminal's beacon camera, run HIL with the real gimbal (rate interface), then field trials; hand over to the fine stage.
50. **Flight readiness?** None claimed — this is a simulation prototype; flight software would need requirements traceability, fault management, deterministic scheduling and qualification.
51. **Safety/fail-safe?** Bounded rate commands, gimbal travel limits, config validation, watchdog-style COAST timeout, deterministic replay, full logging.
52. **How do you avoid detector latency hurting control?** Latency compensation in the controller; ROI keeps processing ~ms.
53. **Why configurable FOV?** PS requirement; also the acquisition/tracking trade-off above.
54. **What about multiple targets?** Supported as look-alike moving targets; designated-target identification via modulation is supported as an option.
55. **What did competitors do and why are you better?** Most public repos use threshold/blob + KF + PID + spiral; some add CNN, IMM, CFAR or wide-FOV modes. We do not claim a better detector; we claim a principled search layer and honest, baseline-compared measurements.
