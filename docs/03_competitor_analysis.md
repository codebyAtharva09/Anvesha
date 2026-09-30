# Public SIH26169 solutions — differentiation analysis

Method: web search (30 Sep 2026) for SIH26169 / "AI-Based Virtual Camera Tracking" / FSOC coarse alignment; README files of public GitHub repositories were read (raw.githubusercontent.com). **Only README claims were read — code was not executed or copied, and README numbers are the authors' claims, not verified by us.** Used solely for differentiation.

## 1. Landscape (20 public repositories found)
| Repo (owner/name) | Detection | Estimation | Control | Search / reacq. | Video (B-2) | UI / stack | Notable |
|---|---|---|---|---|---|---|---|
| ThatKJ/FSOC | classical + TinyBeaconNet (27 k-param ONNX heat-map) | alpha-beta | PID | acquisition checks | — (run-then-playback) | C++20 core, Next.js/R3F | honest "measured results", classical/AI agreement rule |
| pranshukesavmishra/SIH-2026 | top-hat → matched filter → CFAR → sub-pixel (CRLB-limited) | **IMM** | two-path Smith predictor | — | yes (demo video) | PySide6, 69 tests | strongest classical design seen; decoy-field scenario |
| karthikeyavelivela/anantham | compact-blob + 3-frame confirmation | Kalman | — | **square spiral; optional wide-FOV acquisition**; blinking-beacon identity | yes (MP4 + truth CSV) | GUI + CLI, seeded, ablation | "no fabricated numbers" policy |
| rangala-nithin15/ASTRAQ | sub-pixel centroid | Kalman | — | wide acquisition | yes | React/three.js, truck/TOGS 3D scene | reports 1.13 s acquisition; notes "4° only" baseline 6.67 s mean; notes ±20 px jitter floor ≈16 px |
| AtulyaSRawat18 (Doomsday Squad) | binary/weighted/gradient centroid, Gaussian fit | KF/EKF/UKF/adaptive labs | PID + FF | raster/spiral/predicted | — | FastAPI + React/Three.js | optional CNN / GRU-LSTM, Monte-Carlo |
| Yash12b/FSOC_Tracker | CNN perception | adaptive Kalman | adaptive PID | search controller | yes | CLI + GUI | logistic-regression failure predictor, adaptive ROI |
| MridulSrivastavaAa & PriyaanshPandey/fsoc_tracker (identical README) | median + top-hat + MAD threshold, ONNX CNN verifier | 4-state KF | FF-PID | full-scene slew | yes | "mission-control" GUI | "ATAC-PSM" turbulence compensator claim (4.8× — unverified) |
| Kaushal2644/Aurya | threshold + CC blobs + confidence, M-of-N lock | KF | PID | — | yes | PyQt5, PyInstaller | resolution-aware video scaling |
| Akhan18/AI-VISTA | threshold/centroid (YOLO deferred) | CV Kalman | proportional | — | MP4 output | — | |
| shruti12719 | classical ring-signature + optional YOLO | Kalman | PTZ | hide-beacon test | yes | FastAPI + React/Three.js, pywebview exe | hosted web app |
| ayushhroy77/SIH26169 | blob candidates | KF + 5-state machine | PID + FF | — | yes (backend) | React 19 / Vite + FastAPI | two simulators (browser JS and Python) |
| geethika-sandireddy/Fsoc | adaptive threshold, IW-CoG | — | — | — | yes | PySide6 WebEngine | |
| Phalgun21-cloud/SIH | adaptive threshold, blob centroid | KF + particle filter switching | PID + slew limit + FF | — | yes | Tkinter, PyInstaller | |
| sachusorav/astratrack | CV | 4-state KF, 7-state FSM | dual-axis PID | reacq. FSM | — | 3D sim | |
| sakshamshaurya40 | CV | Kalman-style | — | Archimedean spiral | — | Tkinter | |
| snehagautam869 | threshold + contours | KF CV/CA | PID | occlusion logic | yes (viewport extraction) | dashboard | |
| sohampaul07, thisIsRajbirMajhi, saanvisablok22 (AFTERGLOW) | README not retrievable / empty | | | | | | |

## 2. What is now *common* (and therefore not a differentiator)
1. Threshold / blob / CoG centroiding; median pre-filter; M-of-N confirmation.
2. Constant-velocity Kalman filter; 5–7-state PAT state machine.
3. PID (often with velocity feed-forward) on the image error.
4. Spiral / raster search; "wide-FOV acquisition" (≥2 repos).
5. YOLO or small CNN "verifier" — frequently optional, rarely shown to add measured value.
6. FastAPI + React/Three.js or PyQt dashboards; PyInstaller exe; MP4 bypass mode.
7. Even IMM, matched filter + CFAR and Smith-predictor control appear in one strong repo.

## 3. What we did **not** find in any public repo README
| Gap | Evidence | ANVESHA response |
|---|---|---|
| A *probabilistic* model of where the beacon may be, used to decide where to look | All describe fixed spiral/raster/"full-scene slew"; none maintains a belief map with negative-information updates | Recursive Bayesian belief map + planner |
| FOV choice driven by *measured* conditions | Wide-FOV used as a fixed mode where present | Disturbance-aware Pd(zoom) model chooses zoom automatically; falls back to narrow FOV when a small beacon would be lost in noise |
| Re-acquisition that starts from the estimator's predicted distribution | Reacq = "restart spiral" / "Kalman coast" | Belief seeded from IMM mean/covariance + advection |
| Explicit separation of *correctable* LOS error vs *uncorrectable* jitter in the estimator | ASTRAQ reports the jitter floor honestly but no repo describes isolating jitter online | Second-difference jitter estimator → adaptive R, so the loop does not chase jitter |
| Platform-motion handled as a *known input* (IMU) rather than as target motion | FF-PID uses target velocity only | IMU-aided gimbal-frame estimator + disturbance feed-forward (option; ablated) |
| Baselines implemented *inside the same harness* and reported with ablations | Most repos show only their own pipeline | Baselines A/B/C + ablations run on identical seeds |

## 4. Implications for our pitch
* Do **not** lead with "YOLO + Kalman + PID", "mission-control GUI", "PyInstaller exe" or "video bypass" — every serious competitor has them. They are hygiene factors: we have them, we show them briefly.
* Lead with **"where to look" as a probabilistic decision** (belief-driven acquisition & re-acquisition with disturbance-aware FOV) and **honest error decomposition** (LOS vs jitter), backed by *our own measured* baseline comparisons.
* Anticipate judges who have seen IMM/CFAR elsewhere: we cite them as prior art and claim only the integration and the search layer.
