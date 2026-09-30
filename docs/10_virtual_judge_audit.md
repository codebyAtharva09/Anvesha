# Virtual-judge audit of the idea deck (v3 → v4)

Framework: the "SIH Virtual Judge" prompt's analytical 100-point scale. This is **not an official SIH score**.

## Scorecard
| Criterion (max) | v3 | v4 | What limits it |
|---|---:|---:|---|
| Problem understanding (10) | 9 | 9 | Strong: the physics argument for an 8–10 s blind search is drawn to scale. |
| Innovation (15) | 11 | 12 | Stated three times in v3. The competitor table overclaimed: a public repo has seeded ablations. |
| Technical depth (15) | 13 | 13 | Deep, but slides 3 and 4 need 8–9 pt text to hold it. |
| Solution clarity (10) | 7 | 8 | v3 slide 1 had no value proposition. v4 adds one plus three numbers. |
| Feasibility (10) | 8 | 8 | Everything is simulation. No real frame has been through the tracker yet. |
| Impact (10) | 6 | 7 | v3 benefits were generic. v4 has an operational benefit backed by a measured number. |
| Scalability (10) | 5 | 7 | v3 barely covered it. v4 adds a panel (hardware/terminal-agnostic, compute headroom, parallel regression). |
| Evidence / validation (10) | 8 | 8 | Strong methods: baselines, ablation, failures shown. **No GitHub or demo link yet.** |
| Presentation (5) | 3 | 3.5 | Slides 2–4 are dense, and slide 4 is small text at presentation distance. |
| Research (5) | 4 | 4 | 12 DOIs plus a 134-paper database. Some references are decorative (e.g. [12]). |
| **Total** | **≈74** | **≈81** | |

## Most dangerous weaknesses
1. **No verifiable links.** Every number is a claim until the GitHub and demo links exist.
2. **Speed is not unique.** The public repo ASTRAQ reports 1.13 s acquisition. Never say "fastest". The differentiator is the method (belief search, noise-aware FOV, belief-seeded re-acquisition), backed by same-seed baselines.
3. **The AI component is small.**
   - The CNN verifier has 23 % false-positive rate on held-out patches.
   - The ablation shows a modest effect: false-lock frames go 614 → 667 without it, and look-alike acquisition goes 2.9 → 5.1 s.
   - Present the "AI" honestly as probabilistic decision-making plus a learned verifier.
4. **Simulation only.** A judge can dismiss results that have never met a real frame.

## Path to 90+ (ordered by marks per hour)
| # | Action | Who | Expected gain |
|---|---|---|---|
| 1 | Push the repo to public GitHub and record a 2-min demo (GUI: clean → fog → occlusion → report). Rebuild with the links so real QR codes appear. | team | +3–4 (evidence, demo) |
| 2 | **Real-footage test:** film a moving LED or laser dot on a dark wall with a phone, run `run_video.bat clip.mp4`, and add one screenshot plus lock % and FPS to slide 4. Label it "real footage, no ground truth". | team | +3 (feasibility, evidence) |
| 3 | Retrain BeaconNet on GPU with more data (`train_gpu.bat`), then report the new held-out recall/FPR. Only report numbers that improve. | team | +1–2 (AI credibility) |
| 4 | Slide 4 at ≥ 10 pt: show 10 representative scenarios on the slide and the full 16 in the backup/report. | dev | +1 (presentation) |
| 5 | Fix the O (look-alikes) and N (all maxima) failures, then re-run the benchmark. | dev + laptop run | +1 |

Realistic ceiling after items 1–4 is about 88–92. A score of 95+ would need hardware-in-the-loop or field evidence, which is beyond an idea-round deck.

Rebuild with links (Windows):
```
set ANVESHA_GITHUB_URL=https://github.com/<user>/<repo>
set ANVESHA_DEMO_URL=https://youtu.be/<id>
python ppt\build_ppt.py
```
