# Brief for the SIH26169 idea-PPT (ANVESHA)

## Inputs (all local, read them)
- Official template (MUST be used, structure preserved): `/mnt/user-data/uploads/Downloads/SIH2026-IDEA-Presentation-Format.pptx`
  - 6 slides max incl. title; headings fixed: TITLE PAGE / IDEA TITLE (Proposed Solution) / TECHNICAL APPROACH / FEASIBILITY AND VIABILITY / IMPACT AND BENEFITS / RESEARCH AND REFERENCES. Slide 7 (instructions) is deleted. Final upload is PDF.
  - Title-slide fields: Problem Statement ID – SIH26169; Title – "Development of an AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile Free Space Optical Communication (FSOC) Terminals"; Theme – Smart Automation / Space Technology; PS Category – Software; Team ID – (leave blank placeholder); Team Name – Regnum Carya.
- Official PS: `/mnt/user-data/uploads/Downloads/26169.pdf` (note Benchmark-2 video mode = 30 % of marks).
- Reference style material: `/mnt/user-data/uploads/Downloads/SIH_Architecture_Diagram_Editable_Template.pptx`, `SIH_Architecture_Template_Reference_Style.pptx`, `sih-winning-ppt-1 (1).pdf`, `/mnt/user-data/uploads/Downloads/SIH/SIH/SWARMNAV_SIH2026_PS26123.pptx` (team's earlier deck), `SIH_MedTech_StandOut_Guide.docx.pdf`, and the 8 "Stand-out framework" images in `/tmp/claude-0/ref/` (grid0.jpg, grid1.jpg): one idea per slide, cite every stat, a "what makes this different" table (existing solution | limitation | our approach), judges decide in ~30 s.
- Virtual-judge rubric for red-teaming: `/mnt/user-data/uploads/Downloads/SIH VIRTUAL JUDGE.pdf`.
- Research outputs: `/home/claude/repo/docs/01_PS_decomposition_and_compliance.md`, `03_competitor_analysis.md`, `04_gap_matrix_novelty_architecture.md`, literature DB `docs/literature/literature_database.csv` (134 real records with DOIs/links).
- MEASURED results (use only these numbers): `/home/claude/repo/results/bench/summary.json` (scenario|pipeline aggregates over 3 seeds), `results/ablation/summary.json` (when present), `results/video_M6/video_summary.json` (Benchmark-2 rehearsal), `models/beaconnet_eval.json`. GUI screenshots in `/home/claude/repo/docs/img/` (when present).

## Story (one idea per slide)
PROBLEM → WHY CURRENT APPROACHES ARE INSUFFICIENT → INSIGHT → ARCHITECTURE → INNOVATION → FEASIBILITY → HOW BENCHMARKED → IMPACT.

Core insight to make obvious in 30 s:
1. The PS asks for ≤2 s acquisition on a 12.5°×12.5° screen with a 4°×3° camera at 5 °/s. Blind spiral/raster at base FOV physically needs ~8–10 s worst case (show the arithmetic). → "WHERE to look" is the real problem, not "how to detect a bright spot".
2. ANVESHA keeps ONE probabilistic belief of where the beacon can be, through SEARCH → TRACK → LOSS → RE-ACQUIRE; it updates it with negative information every frame and chooses pointing + FOV (zoom) from a disturbance-aware detection-probability model (wide FOV in clear air, narrow FOV in fog/noise).
3. Honest error decomposition: correctable LOS error vs uncorrectable camera jitter (±20 px/frame jitter ≈ 16 px RMS alone — no coarse gimbal can beat that; a fine stage must). Jitter-aware estimator stops the gimbal chasing jitter.
4. Hygiene factors (have them, show briefly, do not lead with them): MF-CFAR detector + tiny CNN verifier (ONNX, CPU), IMM estimator, predictive controller with IMU feed-forward, 7 trajectories, all PS disturbances, video bypass (Benchmark-2), auto performance report, mission-control GUI, standalone exe path.

## Slide plan (suggested — improve it)
1. Title page (template fields). Project name "ANVESHA — Belief-Driven Coarse PAT for Mobile FSOC Terminals".
2. IDEA TITLE / Proposed solution: one-sentence idea; closed-loop diagram (beacon → camera → perception → estimation → belief/search + control → gimbal → camera, disturbances injected, metrics out); 3 innovations; "What makes this different" 3-row table vs typical approaches (spiral+threshold+KF+PID).
3. TECHNICAL APPROACH: architecture diagram (use architecture-template style), tech stack with why (Python/NumPy/OpenCV, ONNX Runtime, FastAPI+WebSocket, vanilla JS + three.js GUI, PyInstaller), multi-rate loop (240/60/30 Hz), GUI screenshot, Benchmark-2 video path.
4. FEASIBILITY: measured evidence table vs PS thresholds (acquisition, LOS error, loss, reacq, FPS, centroid error in video mode) — ANVESHA vs baselines A/B/C on identical seeds; risks & mitigations (sim-to-real, jitter floor, CPU budget, CNN domain shift); honest status labels (implemented / prototype / planned).
5. IMPACT: cost/time of hardware-free PAT algorithm development, repeatable disturbance testing, ISRO/DoS use-cases (mobile ground terminals, UAV/HAP relays, LEO downlinks), education; SIL→HIL roadmap (real camera, pan-tilt, beacon, FSM fine stage) with same software interfaces.
6. RESEARCH AND REFERENCES: 8–12 strongest real references (short form + DOI), one line "134-paper database + 20 public SIH26169 repos analysed"; compliance coverage badge.

## Rules
- Use ONLY numbers present in the results JSON files; label them "measured in simulation (software-in-the-loop), 3 seeds". Never invent results, papers or ISRO specs. If a number is missing, show the metric without a value rather than guessing.
- No absolute novelty claims. Use: "Based on our review of 134 papers and 20 public SIH26169 repositories, we did not identify …".
- Do not name or disparage specific competitor teams on slides; refer to "typical public approaches".
- Minimal text; diagrams, tables, icons (simple shapes), ≥ 14 pt body where possible; consistent palette (the template's), high contrast.
- Keep template branding/header/footer elements intact; do not change the idea-detail pointer headings.
- Output: `/home/claude/repo/ppt/SIH26169_RegnumCarya_ANVESHA.pptx` and a PDF export (LibreOffice: `soffice --headless --convert-to pdf`), plus render PNG previews and inspect every slide visually (fix overflow/overlap).
- Also write `/home/claude/repo/ppt/presenter_script.md` (slide-by-slide, ~60–90 s each) and `/home/claude/repo/ppt/redteam_review.md` (review as ISRO scientist, CV researcher, aerospace engineer, SW engineer, SIH evaluator, skeptic, competitor, using the Virtual-Judge rubric) and then revise the deck accordingly.
- Build the deck with a Python script `/home/claude/repo/ppt/build_ppt.py` (python-pptx, editing a copy of the official template) that reads the results JSON so numbers can be refreshed by re-running it.
- Do not add any mention of Claude/AI-assistant authorship anywhere in files.
