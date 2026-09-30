# Red-team review — ANVESHA idea deck (SIH26169, Regnum Carya)

Method: the rubric in *SIH VIRTUAL JUDGE.pdf* (slide-by-slide forensic audit, claim audit,
technical / AI credibility audit, innovation audit, competitor audit) applied to the rendered
deck by seven reviewer personas. The first complete draft (v1, built after
`results/bench/summary.json` arrived) was reviewed; issues were fixed in `build_ppt.py` and the
deck was rebuilt (v2). Section 4 lists every change. Section 5 lists what is still open.

Rubric labels used: FACT (verifiable in repo data), CLAIM (stated, needs evidence), EVIDENCE
(measured number on slide), ASSUMPTION, MISSING, RISK.

---

## 1. Core story check (rubric §2)

PROBLEM (≤ 2 s acquisition on a 12.5° screen with a 4° × 3° camera at 5 °/s) → WHY EXISTING
APPROACH IS INSUFFICIENT (blind spiral needs ~8–10 s; measured spiral baselines median 7.8–9.2 s)
→ SOLUTION (one belief map drives pointing + FOV) → INNOVATION (3 items + difference table) → HOW
IT WORKS (slide 3 architecture) → PROOF (slide 4 scenario matrix, same-seed baselines, video
rehearsal, measured gaps) → IMPACT (slide 5) → SCALABILITY (SIL → HIL roadmap).

*What should the evaluator remember?* "They showed that ≤ 2 s is a where-to-look problem, solved
it with a belief map, and showed honestly where it still fails." v1 did make the first half clear;
v1 slide 2 contradicted the second half (see issue R1).

---

## 2. Persona reviews (v1 → findings)

### 2.1 ISRO scientist (PAT / optical communication)
- **R1 (dangerous, CLAIM vs EVIDENCE):** v1 slide 2 said the FOV logic uses "narrow FOV in fog /
  noise", implying the system works in fog. The benchmark shows 0/3 acquisitions in G_fog and
  L_rain. A PAT scientist would read this as over-claiming. → Reworded to what the mechanism does
  ("go wide only when the beacon stays detectable") and put the fog/rain failures on slide 4.
- **R2:** Acronyms LOS, IMM, MF-CFAR, IW-CoG, R undefined. → Glossary line added on slide 3.
- **R3:** "Coarse gimbal cannot beat jitter" needs the arithmetic. → Slide 4 states it is analytic
  (±20 px uniform → 20/√3 × √2 = 16.3 px RMS) and shows the measured split at ±10 px
  (image 8.9 px vs LOS 4.6 px).
- **R4:** The 22 s on-orbit acquisition figure (Wang et al., Opt. Lett. 2023) is a different link
  geometry. → Kept as context only ("why acquisition matters"); presenter script says explicitly it
  is not a like-for-like comparison.

### 2.2 Computer-vision researcher
- **R5 (AI credibility):** v1 mentioned a CNN verifier with no training/validation evidence. The
  rubric flags any model without validation. → Slide 4 status now shows "recall 90 %, FPR 23 % on
  held-out synthetic patches" from `models/beaconnet_eval.json`, labelled *Prototype*, and slide 3
  says the CNN only verifies while MF-CFAR stays primary. The FPR is not flattering; it is shown.
- **R6:** "Tracking error" is ambiguous (image-plane vs boresight). → Matrix has separate LOS and
  image columns; footnote defines LOS.
- **R7:** Video-mode 0.14 px centroid RMSE looks "too good". → Tile says it is a rehearsal on our
  own generated 2000 × 2000 clip; presenter script notes filtered-estimate error (~5 px RMSE) is
  also logged and evaluator videos may differ.

### 2.3 Aerospace / controls engineer
- **R8:** Fairness of the acquisition comparison: baselines are locked to the 4° × 3° FOV while
  ANVESHA may widen it; part of the gain may be the FOV, not the belief. → SIL line on slide 4 now
  states baseline gains were grid-tuned; the ablation block (adaptive FOV off / belief → spiral)
  quantifies the split when `results/ablation/summary.json` is present. Presenter script prepares
  the answer.
- **R9:** LOS error > 10 px under vibration (F2 20.4 px), fast manoeuvre (J 18.6 px), occlusion
  (K 17.0 px) was not visible in v1's aggregate numbers. → The per-scenario matrix makes each one
  red; the gaps box names them.
- **R10:** Slide 1–5 in v1 spoke of "same Camera / Gimbal interfaces". The code has no formal
  interface classes; the engine exchanges frames, encoder angle, IMU rate and rate commands with
  `SimWorld`. → Reworded on slides 4 and 5 and in the script to exactly that boundary.

### 2.4 Software engineer
- **R11:** FPS without hardware context is weak evidence. → Slide 4 SIL line: "CPU only (2 cores)";
  matrix uses the conservative *loop* FPS (includes scene rendering, two benchmark runs in
  parallel); lowest value 34 FPS.
- **R12:** Standalone .exe is a mandatory deliverable but `packaging/` is empty. → Marked
  *Planned* on slide 3 (tech table) and slide 4 (status). No claim of a working exe anywhere.
- **R13:** `tests/` is empty. → Deck makes no claim about unit tests.
- **R14:** Slide 3 bottom text overflowed into the footer in v1 render. → Layout tightened.

### 2.5 SIH evaluator (template compliance)
- **R15:** Template headings and pointer texts must stay. → All six headings kept; every pointer
  text is present verbatim (on slide 4 the two risk pointers are used verbatim as the risk-table
  column headers to save space). Instructions slide deleted. Team ID left blank (`________`).
- **R16:** v1 title slide: template title ran under the SIH logo. → Title box narrowed and font set
  to 38 pt; no other branding touched. Footer text kept as in the template.
- **R17:** Slide 2 had no explicit idea *title* under the heading "IDEA TITLE". → Headline now
  starts "ANVESHA: …".

### 2.6 Skeptical judge
- **R18 (dangerous):** v1 slide 4 averaged acquisition time only over acquired runs, which hides
  total failures (fog, rain). → Replaced by "% of 48 runs acquired within 2 s" (failures count as
  misses) and a k/3 count per scenario.
- **R19:** "All PS specs met?" is the question a judge will ask. → Explicit line: ANVESHA meets all
  PS checks in 9/16 scenarios; baselines 0/16. Coverage badge on slide 6 repeats "(all met in
  9/16)" instead of a blanket "5/5 specs".
- **R20:** Only 3 seeds. → Stated on every evidence slide; presenter script: enough for large
  effects (77 % vs 12–15 %), not small ones.
- **R21:** Novelty. → Only the agreed wording is used ("Based on our review of 134 papers and 20
  public SIH26169 repositories, we did not identify …"). Prior art (MF-CFAR, IMM, CNN verifier,
  IMU feed-forward, predictive control) is named as *not claimed novel* on slide 3.

### 2.7 Competing team
- **R22:** "Wide-FOV acquisition" already exists in public repos (one reports ~1.1 s). Our v1 table
  row 2 said "a 10 px beacon is lost in fog / noise" as the competitors' limitation — but our own
  system also loses it in fog. → Row now reads "SNR loss of a wider FOV is not modelled" vs "FOV
  picked from a measured-noise detection model": a design difference, not a performance claim.
- **R23:** Competitors are not named anywhere; they are "typical public approaches".
- **R24:** A competitor would attack the fog/rain/distractor failures. They are already on the
  slide with the planned next step, which removes the attack.

---

## 3. Scores (rubric §5, v2 deck; 0–10, not inflated)

| Slide | Content | Clarity | Technical | Innovation | Visual | Evidence | Overall |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 Title | 8 | 9 | – | 5 | 8 | – | 8 |
| 2 Idea | 8 | 7 | 8 | 8 | 7 | 7 | 7.5 |
| 3 Technical | 8 | 7 | 9 | 6 | 7 | 6 | 7.5 |
| 4 Feasibility | 9 | 6 | 8 | 6 | 7 | 9 | 7.5 |
| 5 Impact | 7 | 8 | 5 | 5 | 8 | 4 | 6.5 |
| 6 References | 8 | 8 | 6 | 6 | 7 | 7 | 7 |

Justification of the lowest cells: slide 4 clarity 6 — it is dense (matrix + chart + tiles + risk
table + gaps); a judge needs the presenter to guide the eye. Slide 5 evidence 4 — benefits are
qualitative by design (no invented cost numbers). Slide 3 innovation 6 — most blocks are prior art
by our own admission; only the orange block is new.

Analytical total (rubric §6 framework, not an official SIH score): Problem understanding 9/10,
Innovation 11/15, Technical depth 13/15, Solution clarity 8/10, Feasibility 7/10, Impact 7/10,
Scalability 6/10, Evidence 8/10, Presentation 4/5, Research 4/5 → **77/100**.
Largest point losses: measured failures in fog/rain/distractors (feasibility), exe/HIL not yet
built (scalability), slide-4 density (presentation).

---

## 4. Claim audit (rubric §10) after revision

| Claim on slide | Evidence in deck | Confidence | Action taken |
|---|---|---|---|
| Blind raster at base FOV needs ~8–10 s | arithmetic + measured spiral median 7.8 / 9.2 s (A/B) | CONFIRMED (SIL) | measured median added to slide 2 |
| 77 % of runs acquired ≤ 2 s vs 12–15 % | `acq_le_2s_pct` mean over 16 scenarios | CONFIRMED (SIL, 3 seeds) | label "48 runs each" |
| Meets all PS checks in 9/16 scenarios | per-scenario matrix | CONFIRMED (SIL) | shown explicitly |
| Disturbance-aware FOV | mechanism described; ablation when available | PARTIALLY SUPPORTED | fog claim removed; ablation block |
| Jitter-aware estimator stops chasing jitter | E_jitter image 8.9 vs LOS 4.6 px; ablation when available | PARTIALLY SUPPORTED | ablation line "jitter-aware R off" |
| Re-acquisition ≤ 1 s | K_occlusion mean 0.07 s, max 0.27 s, 0/6 unrecovered | CONFIRMED (SIL, one scenario) | stated as scenario K |
| AI (CNN verifier) | recall 90 %, FPR 23 % held-out synthetic | PARTIALLY SUPPORTED | labelled Prototype |
| Benchmark-2 ready | 0.14 px RMSE, 29 FPS on own 2000 × 2000 video | PARTIALLY SUPPORTED (own video only) | "rehearsal" wording |
| Standalone .exe | none | UNSUPPORTED → not claimed | "planned" |
| HIL-ready | engine boundary exists; no rig | REQUIRES VERIFICATION | roadmap step 3, not "done" |
| No coarse gimbal meets 10 px image error at ±20 px jitter | analytic 16.3 px | CONFIRMED (analytic) | labelled analytic |
| Novelty | literature DB + 20 README reviews | wording-limited | agreed non-absolute wording only |

---

## 5. Changes made (v1 → v2), all in `build_ppt.py`

1. Slide 2 innovation #2 and difference-table row 2 reworded (R1, R22).
2. Slide 2 headline starts with the idea title "ANVESHA: …" (R17); measured badge added.
3. Slide 2 panel 1: measured spiral baseline medians added next to the physics estimate.
4. Slide 3: glossary line; prior art labelled "not claimed as novel"; layout fixed so nothing
   overflows into the footer (R2, R14, R21).
5. Slide 4 rebuilt: per-scenario × PS-check matrix for ANVESHA (green/red), all-pipeline
   "% runs ≤ 2 s" chart (matplotlib, from JSON), re-acquisition and Benchmark-2 tiles, measured-gaps
   box with fog/rain/distractor/all-maxima failures, LOS > 10 px cases and the jitter floor; SIL
   line with seeds, grid-tuned baselines and CPU context; ablation block auto-filled from
   `results/ablation/summary.json` (R5, R8, R9, R11, R18, R19).
6. Slide 4 status: CNN verifier metrics; .exe / HIL / real footage marked Planned (R5, R12).
7. Slides 4–5 and script: "same Camera/Gimbal interfaces" replaced by the actual engine boundary
   (R10).
8. Slide 6: coverage badge now "5 performance specs measured per scenario (all met in 9/16)"
   instead of "5/5" (R19); stat tile wording for the ablation.
9. Slide 1: template title no longer runs under the SIH logo (R16).
10. Speaker notes filled from `presenter_script.md` automatically.

---

## 6. Open issues (not fixable in the deck)

- **Fog (G) and rain (L): 0 % acquisition; look-alike distractors (O) and all-maxima (N): 33 %.**
  These are algorithm issues. If the pipeline is improved and the benchmark re-run, re-run
  `python ppt/build_ppt.py` — every number, colour and the 9/16 count refresh automatically, but
  the wording of the gaps bullet on slide 4 names these four scenarios and must be re-checked.
- **LOS error > 10 px in F2 / J / K.** Same as above.
- **Ablation not available at final build** (`results/ablation/summary.json` did not exist after
  ~60 min of polling). Slide 4 therefore shows the median-acquisition line instead of the ablation
  block, and slide 6 does not mention an ablation. Once the file exists, re-run
  `python ppt/build_ppt.py`; the block (belief → spiral, adaptive FOV off, jitter-aware R off,
  IMU feed-forward off, CNN verifier off) fills automatically. Until then R8 (how much of the
  acquisition gain is FOV vs belief) is answered only verbally — a real weakness.
- **Standalone .exe** not built; packaging directory empty.
- **Footer** still reads "@SIH Idea submission- Template" because the brief says to keep template
  footer elements intact; the team may choose to leave it.
- **Team ID** blank by design; fill it before exporting the final PDF.
