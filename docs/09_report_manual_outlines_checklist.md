# Technical report outline (10–15 pages, PS deliverable)

1. **Problem understanding** (1 p) — coarse vs fine PAT; SIH26169 requirements; hidden requirements (Benchmark-2 video, acquisition physics, jitter floor). Source: doc 01.
2. **State of the art & gap** (1.5 p) — doc 02 + gap matrix (doc 04 §1); competitor landscape summary (doc 03, no team names).
3. **System architecture** (1.5 p) — block diagram, multi-rate loop, data flow, truth isolation, module map.
4. **Software modules** (2.5 p) — sim (world/optics/disturbances/platform), perception (MF-CFAR, centroid, BeaconNet), estimation (IMM, jitter-aware R), search (joint belief, planner), control (predictive), supervisor (mode machine, re-anchor, look-alike rejection), metrics/logging/report, GUI, video mode.
5. **Tracking methods** (1 p) — equations: matched filter & CFAR, IW-CoG, IMM mixing, second-difference jitter estimator, controller law.
6. **AI methods** (1 p) — BeaconNet architecture, synthetic training data, held-out results, veto fusion, why not YOLO.
7. **Search / acquisition method** (1.5 p) — belief recursion, detection-probability model with contrast hypotheses, planner objective, re-acquisition seeding; worked example (clear vs fog).
8. **Test methodology** (1 p) — scenarios A–O, seeds, baselines & tuning, metric definitions, Benchmark-2 rehearsal (doc 05).
9. **Performance analysis** (2 p) — auto-inserted tables/charts from `results/`; PS pass/fail; ablation; failure cases and physical limits (jitter floor, vibration above gimbal bandwidth).
10. **Limitations & future improvements** (0.5 p) — sim-to-real calibration, modulation-based identification, HIL, FSM hand-off, GPU-trained verifier.
Appendix: configuration reference, CLI, reproducibility instructions.

# User manual outline
1. Installation — Python 3.10+, `install.bat` (pip requirements) or the standalone `ANVESHA.exe` (build with `packaging\build_exe.bat`).
2. Quick start — `run_gui.bat` → browser opens; choose scenario + pipeline → START.
3. GUI tour — header (run ID, sim time, mode chip), camera view overlays (boresight, 10 px box, measurement, prediction/gate, candidates), world view (belief map, FOV, next look, truth marker for display only), 2D/3D toggle, telemetry table, IMM bars, pan/tilt glyph, performance charts, KPI tiles vs PS limits, event log.
4. Live controls — noise (Gaussian σ, Poisson, S&P %, jitter), atmosphere (condition, severity, turbulence), platform (mode, px/frame), target (trajectory, speed), HOLD-to-occlude, LOS shock, adaptive-FOV toggle, speed, pause.
5. Reports — REPORT button → HTML/PDF/CSV in `results\gui_runs\<run id>`; field descriptions.
6. Scenario files — YAML format, every key (config reference), validation errors.
7. Benchmarks — `run_benchmark.bat`, outputs, BENCHMARK tab.
8. Video mode (Benchmark-2) — `run_video.bat video.mp4 [truth.csv]`, VIDEO tab, output columns.
9. Retraining BeaconNet — `train_gpu.bat` (CUDA if available).
10. Troubleshooting — port in use, missing model (falls back to classical), slow PC (reduce speed / disable 3D).

# Final submission checklist
- [ ] Team ID filled on title slide; team name "Regnum Carya".
- [ ] Deck ≤ 6 slides, template headings intact, instructions slide removed, exported to **PDF**.
- [ ] Every number on slides traceable to `results/*.json`; labels say "measured in simulation".
- [ ] References have DOIs/links; novelty wording is non-absolute.
- [ ] `run_gui.bat`, `run_benchmark.bat`, `run_video.bat` tested on the demo laptop (offline).
- [ ] `ANVESHA.exe` built on Windows and smoke-tested (optional for idea round; mandatory later).
- [ ] 2–3 demo scenarios rehearsed (A_clean, M_combined, K_occlusion; G_fog to show adaptive FOV).
- [ ] Benchmark-2 rehearsal video + truth ready; video mode timing verified on the demo laptop.
- [ ] Presenter script rehearsed to time; judge Q&A (doc 08) reviewed by every member.
- [ ] Repo cleaned (no large videos), README up to date, `pytest` passes.
