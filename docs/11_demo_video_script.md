# 2-minute demo video: shot list

Record the screen with the Windows Game Bar (Win+Alt+R) or OBS at 1080p. Use your voice or captions, and no music.
Before recording, run `run_gui.bat`, set the browser to full screen, and close other tabs.

| Time | Screen | Say (short) |
|---|---|---|
| 0:00–0:10 | Title slide of the deck | "ANVESHA: coarse pointing, acquisition and tracking for mobile FSOC terminals. SIH26169, team Regnum Carya." |
| 0:10–0:25 | GUI, scenario **A_clean**, ANVESHA pipeline, press START | "A 640×480 virtual camera with a 4°×3° field of view, on a 5 °/s gimbal, has to find the beacon somewhere on a 12.5° screen." |
| 0:25–0:45 | Keep the **world view / belief map** visible while it searches | "Every empty frame removes probability from where the camera looked. The next look is the place and zoom with the best chance of detection per second." |
| 0:45–1:00 | Lock happens: TRACK chip, 10 px box, IMM bars | "Locked in about a second. From here the IMM tracker and predictive controller keep it centred." |
| 1:00–1:15 | Switch to **G_fog** (or raise fog severity live) | "In fog the beacon is faint, so the planner learns from misses and stays at narrow zoom instead of zooming out blindly." |
| 1:15–1:30 | Press **HOLD-to-occlude** for ~1 s, then release | "Occlusion: the tracker coasts, then re-acquires from its own prediction, typically in about 0.1 s." |
| 1:30–1:45 | **BENCHMARK** tab or `results\bench\benchmark_report.html` | "Same seeds for every pipeline: 87 % of runs acquired within 2 s, against 12–15 % for the spiral baselines. The failures are shown too." |
| 1:45–2:00 | **VIDEO** tab running an .mp4 (Benchmark-2 mode) | "Benchmark-2 mode bypasses the camera and tracks the evaluator's video directly. Everything runs offline on a laptop CPU." |

Upload the video to YouTube as **Unlisted** and put the link on slide 6: `set ANVESHA_DEMO_URL=...`, then `python ppt\build_ppt.py`.
Say "simulation" whenever you quote a number. If the benchmark is re-run, quote the numbers from the new report, not this script.
