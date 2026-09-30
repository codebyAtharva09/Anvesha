# State-of-the-art report — coarse PAT for mobile FSOC (2015–2026)

Scope: 134 records in `docs/literature/literature_database.xlsx` (IDs `L###` below). Evidence level is stated per record: 39 were summarised from publisher abstracts, 95 from bibliographic metadata only. **No full texts were reviewed**, so this report draws conclusions only where titles/abstracts support them; anything quantitative must be checked in the full paper before being quoted.

## 1. Where coarse acquisition sits in PAT
Surveys (L001 Kaymak 2018; L002 Abdelfatah 2022; L003 Eguri 2022; L004 Li 2022) describe PAT as a two-stage chain: a **coarse stage** (gimbal / body pointing, wide-field camera or beacon imager) brings the partner inside the field of view of a **fine stage** (FSM + QD/PSD/camera, L005, L109, L110). Real mobile systems follow this pattern: electro-optical pod + inner fine module on moving platforms (L018), shipborne ATP to LEO (L009), airborne APT (L008, L016, L043), CubeSat beacon-camera PAT (L012, L013), body pointing on small-sats (L011). SIH26169 asks for the coarse stage, in software.

## 2. Acquisition
* **Open-loop scan patterns** dominate the literature: spiral / composite spiral (L044), sub-region scanning under vibration (L045), dual-way scanning (L048), Lissajous (L051), scan-pattern optimisation (L052, L130). Acquisition time and hit probability are modelled analytically under vibration and jitter (L046, L047, L053, L054, L055). On orbit, acquisition times of tens of seconds are still reported (L041: 22 s).
* **Prior-aware scanning** is recent: probability-ordered scanning of an elliptical field of uncertainty (L049, TAES 2025) and FOU-shaped patterns (L050). From the metadata these use a *static* prior; we found no record of a recursive update with negative information.
* **Multi-field / wide-FOV acquisition** exists (L131, L132; indoor OWC L032), generally with rule-based switching.
* **Computer-vision sensor management** (L133 information-theoretic PTZ control; L134 active PTZ search) is the closest methodological prior art for choosing where and how wide to look — but in surveillance, not FSOC.
**Gap:** a closed-loop belief over beacon position that is updated each frame with negative information, drives both pointing and FOV choice through a detection-probability model, and is re-used for re-acquisition — not identified in the reviewed records.

## 3. Beacon detection and centroiding
* Classical: thresholding, spot detection, centroid variants (L061, L064, L071, L074), Gaussian fitting (L068), weak-beacon centroiding (L059, L063), turbulence-induced centroid error (L058, L065), optical-flow beacon recognition (L060).
* Learned: CNN star detection/centroiding in real time on CubeSat hardware (L069), ANN centroiding (L072), DL beacon finding with reflections (L076); heavy IR small-target networks (L078 DNANet, L079 UIU-Net) and low-rank methods (L080, L081) — strong but costly for a 20 FPS CPU budget; tiny-object survey (L086) explains why generic detectors (L088 YOLO) struggle at 5–20 px.
* Impulse-noise handling: switching/adaptive median filters (L121). Mixed Poisson–Gaussian sensor noise (L120).
**Take-away:** for a known, compact spot the matched filter + CFAR with robust noise estimation is near-optimal and cheap; learning is most useful as a *verifier* against structured clutter. We adopt that and measure it by ablation.

## 4. Tracking / estimation
KF-based beacon tracking with adaptive noise (L095 noise-adaptive fading KF — direct prior art for adaptive R), KF prediction of pointing angle (L096), IMM variants (L097, L098), adaptive UKF (L099), KF review (L100), KF + CamShift spot tracking (L067), full-image → ROI tracking frameworks (L084), particle filters for dim targets (L082). Appearance trackers (L090–L092) target textured objects and are ill-suited to a featureless spot.

## 5. Control
Predictive / MPC pan-tilt and gimbal tracking (L101, L102, L104), delayed-feedback compensation (L105), inertial stabilisation with disturbance feed-forward / observers (L103, L106, L108, L111), ADRC/SMC for fine stages (L107, L109, L110), DRL coarse-to-fine tracking (L112 — rejected here for verifiability).

## 6. Disturbances
Platform jitter / hovering statistics (L023, L024, L113), vibration-driven acquisition loss (L045–L047, L054), turbulence & scintillation (L058, L065, L114, L125), fog + turbulence joint models (L117), Indian weather conditions (L116), haze image formation / dehazing (L118, L119), physics-based adverse-weather simulation for learning (L122).

## 7. Simulation, SIL/HIL
HIL/SIL for space hardware reduces cost and risk (L123, L124); equivalent ground testing of APT (L015); turbulence emulation benches (L125); numerical PAT simulation for ship-satellite links (L126); digital twins for OWC (L127).

## 8. What this means for SIH26169
1. The *detection* problem for a bright square spot is largely solved classically; robustness to impulse noise, streaks and look-alikes is where engineering matters.
2. The *acquisition* problem under the PS's numbers (12.5° screen, 4°×3° FOV, 5 °/s, ≤2 s) is where current practice (open-loop scans) is physically insufficient — this is where ANVESHA focuses.
3. Honest separation of what a coarse gimbal can and cannot correct (jitter/vibration above its bandwidth belong to the fine stage, L005, L029) is necessary to interpret the PS's ≤10 px criterion.
